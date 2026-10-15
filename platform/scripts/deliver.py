"""Produce the delivery: every ruling as a Word file with its abstract on top, and the
same ruling in French.

    python deliver.py --out ../../delivery                 # everything
    python deliver.py --out ../../delivery --limit 50      # a pilot
    python deliver.py --out ../../delivery --arabic-only   # no translation, no cost

For each ruling it writes two files, mirroring results/documents/<chamber>/:

    delivery/ar/<chamber>/<doc>.docx       the abstract in bold, then the ruling
    delivery/fr/<chamber>/<doc>.fr.docx    the same, in French
    delivery/report.csv                    one row per ruling: what was written, what failed

results/ is read and never written to; the hand-off stays exactly as it was.

The abstract is the court's own rule where it printed one, and a written summary where
it did not. A written one is marked as such under the bold text -- «ملخص محرر آليا» /
«Résumé rédigé automatiquement» -- because in a Word file there is nothing else to tell
a reader that these are not the court's words. --no-mark drops the mark.

Translation runs on Vertex AI, through the account gcloud is signed in to. The rate it
can sustain was measured rather than assumed: 652 rulings at up to 300 in parallel, no
request refused, throughput levelling off near 9.5 rulings a second at about 96 in
parallel. That is the default; more buys nothing.

A French file is only written if it is whole. Every name the anonymizer removed is an
XXXXXXX in the Arabic, and the translation must carry exactly as many -- a free
translator tested on this corpus lost 4 of 44, which leaves a sentence reading as if no
one had been named. A translation that loses one, or comes back cut short, is retried,
and if it still fails it is reported instead of shipped.

Safe to interrupt: a ruling whose French file exists is skipped on the next run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

try:
    _here = Path(__file__).resolve().parent
except NameError:
    _here = Path.cwd()
_backend = _here.parent / "backend"
if (_backend / "db.py").exists():
    sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db         # noqa: E402
import translate  # noqa: E402
from sqlalchemy import select  # noqa: E402

PROJECT = os.getenv("VERTEX_PROJECT", "project-40a7c957-819f-4627-b24")
LOCATION = os.getenv("VERTEX_LOCATION_DELIVERY", "global")
MODEL = os.getenv("DELIVERY_MODEL", "gemini-2.5-flash-lite")
# Every region runs its own shared pool. One pool was enough when this was measured;
# later the same night one pool alone throttled us to a third of that, with a 429 on
# one ruling in thirty. Spreading requests over all of them -- and sending a throttled
# request to a different region rather than waiting on the same one -- multiplies the
# capacity. All fifteen were checked to serve this model for this project.
REGIONS = [r.strip() for r in os.getenv(
    "DELIVERY_REGIONS",
    "global,us-central1,us-east1,us-east4,us-east5,us-south1,us-west1,us-west4,"
    "europe-west1,europe-west4,europe-west8,europe-west9,europe-north1,"
    "europe-central2,europe-southwest1").split(",") if r.strip()]


def url_for(region: str) -> str:
    host = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
    return (f"https://{host}/v1/projects/{PROJECT}/locations/{region}/"
            f"publishers/google/models/{MODEL}:generateContent")


_turn = [0]
_turn_lock = threading.Lock()


def next_region() -> str:
    with _turn_lock:
        _turn[0] += 1
        return REGIONS[_turn[0] % len(REGIONS)]


URL = url_for(LOCATION)

# The AI Studio key is a second, separate channel with its own quota. After hours of
# sustained use Vertex throttled this project hard -- 8 of 60 requests through, where
# the same burst earlier passed 96 of 96 -- while the key, tested at the same moment,
# passed 80 of 80. So the key goes first, and a request refused by one goes to the other.
KEY_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
API_KEY = os.getenv("TRANSLATE_API_KEY") or os.getenv("GEMINI_API_KEY", "")

REDACTION = "XXXXXXX"
# A line of its own between the abstract and the ruling, so one request translates both
# and they can be told apart afterwards. Symbols survive translation untouched.
SEPARATOR = "####"
# Longer than this and a ruling is translated in pieces: one reply has a ceiling on how
# much it can say, and the longest ruling here would come close to it.
CHUNK = 30000
# A French ruling much shorter than the Arabic was cut off, not translated.
MIN_RATIO = 0.6

MARK_AR = "ملخص محرر آليا — لا يصدر عن المحكمة"
MARK_FR = "Résumé rédigé automatiquement — ne provient pas de la Cour"

from restyle_abstracts import ABSTRACT_PT, TITLE, TITLE_PT, _size, french_layout  # noqa: E402  one layout
PRICE_IN, PRICE_OUT = 0.10, 0.40          # per million tokens, Flash-Lite

# The site's translation prompt tells the model to keep XXXXXXX. Here every XXXXXXX has
# been numbered first (see protect), and a model told only about XXXXXXX rewrites the
# numbers -- tested, it turned every §k§ in a ruling back into something else. So the
# delivery says what the markers are.
PROMPT = translate.PROMPT.replace(
    "- Leave XXXXXXX exactly as it is. It marks a name that was removed.",
    # No example numbers here: given "§17§" as an example, the model wrote §17§ into a
    # ruling that only had nine markers.
    "- Some words are markers: a § sign, a number, and another § sign. Each one stands "
    "for a name that was removed. Copy every marker exactly as it appears in the text, "
    "once, in the matching place. Never drop, merge, renumber, translate or add one.")
assert PROMPT != translate.PROMPT, "the prompt line to replace was not found"


# ─── authentication ────────────────────────────────────────────────────────────────

class Token:
    """A gcloud access token, renewed before it lapses.

    The run takes about an hour and a token lasts about an hour, so it is fetched again
    every 40 minutes, and at once if Vertex answers 401.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.value, self.at = "", 0.0
        self.gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"

    def get(self, force: bool = False) -> str:
        with self.lock:
            if force or not self.value or time.time() - self.at > 40 * 60:
                out = subprocess.run([self.gcloud, "auth", "print-access-token"],
                                     capture_output=True, text=True, timeout=60)
                if out.returncode or not out.stdout.strip():
                    raise RuntimeError(f"gcloud gave no token: {out.stderr.strip()[:200]}")
                self.value, self.at = out.stdout.strip(), time.time()
            return self.value


# ─── translation ───────────────────────────────────────────────────────────────────

def pieces(abstract: str, body: str) -> list:
    """What to send. The abstract rides with the first piece, ahead of the separator."""
    chunks = translate.split_for_translation(body, CHUNK) or [""]
    head = f"{abstract}\n{SEPARATOR}\n" if abstract else ""
    return [head + chunks[0]] + chunks[1:]


def split_answer(text: str, had_abstract: bool) -> tuple:
    """(abstract, body) from the first piece's translation, or None if the separator
    did not come back exactly once."""
    if not had_abstract:
        return "", text
    parts = [p for p in text.split("\n")]
    hits = [i for i, l in enumerate(parts) if l.strip() == SEPARATOR]
    if len(hits) != 1:
        return None
    i = hits[0]
    return "\n".join(parts[:i]).strip(), "\n".join(parts[i + 1:]).strip()


def whole(source: str, translated: str) -> str:
    """Why a translation cannot be shipped, or "" if it can."""
    if not translated.strip():
        return "empty"
    if translated.count(REDACTION) != source.count(REDACTION):
        return f"redactions {source.count(REDACTION)}->{translated.count(REDACTION)}"
    if len(translated) < MIN_RATIO * len(source):
        return f"too short {len(translated)}/{len(source)}"
    return ""


def call(client, token: Token, text: str, prompt: str = None) -> tuple:
    """One translation request. Returns (text, tokens_in, tokens_out, error)."""
    body = {"contents": [{"role": "user", "parts": [{"text": (prompt or PROMPT) + text}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 65535}}
    err = ""
    for attempt in range(12):
        # even attempts on the key, odd ones on Vertex; with no key, Vertex every time
        try:
            if API_KEY and attempt % 2 == 0:
                r = client.post(KEY_URL, params={"key": API_KEY}, json=body, timeout=600)
            else:
                r = client.post(url_for(next_region()),
                                headers={"Authorization": f"Bearer {token.get()}"},
                                json=body, timeout=600)
        except Exception as e:
            err = type(e).__name__
            time.sleep(1 + random.random())
            continue
        if r.status_code == 401:
            token.get(force=True)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            # another region, almost at once: the next pool is probably not busy
            err = f"HTTP {r.status_code}"
            time.sleep(0.5 + random.random() * (1 if attempt < len(REGIONS) else 8))
            continue
        if r.status_code >= 400:
            return "", 0, 0, f"HTTP {r.status_code}: {r.text[:120]}"
        d = r.json()
        u = d.get("usageMetadata") or {}
        cand = (d.get("candidates") or [{}])[0]
        out = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or [])
        if cand.get("finishReason") == "MAX_TOKENS":
            return out, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), "cut off"
        return out.strip(), u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), ""
    return "", 0, 0, f"gave up ({err})"


def protect(text: str) -> tuple:
    """Give every XXXXXXX its own number, so none can be merged with its neighbours.

    Names often come in runs -- XXXXXXX و XXXXXXX و XXXXXXX -- and a model asked to
    translate identical tokens side by side will sometimes drop or repeat some. With
    §1§ §2§ §3§ there is nothing to merge, and each one can be checked individually.
    """
    n = [0]

    def number(_m):
        n[0] += 1
        return f"§{n[0]}§"
    return re.sub(REDACTION, number, text), n[0]


def restore(text: str, n: int):
    """Back to XXXXXXX -- or None unless every number came back exactly once."""
    for k in range(1, n + 1):
        if text.count(f"§{k}§") != 1:
            return None
    if len(re.findall(r"§\d+§", text)) != n:
        return None
    return re.sub(r"§\d+§", REDACTION, text)


def _translate_text(client, token: Token, text: str, numbered: bool = True) -> tuple:
    """One text, in pieces if long. (french, in, out, error)

    numbered: each XXXXXXX is sent as §k§ and must come back exactly once.
    plain:    XXXXXXX is sent as is, under the site's prompt; the count is checked after.
    """
    if not text.strip():
        return "", 0, 0, ""
    if not numbered:
        tin = tout = 0
        parts = []
        for p in translate.split_for_translation(text, CHUNK) or [text]:
            out, a, b, err = call(client, token, p, prompt=translate.PROMPT)
            tin, tout = tin + a, tout + b
            if err:
                return "", tin, tout, err
            parts.append(out)
        fr = "\n".join(parts)
        if fr.count(REDACTION) != text.count(REDACTION):
            return "", tin, tout, f"redactions {text.count(REDACTION)}->{fr.count(REDACTION)}"
        return fr, tin, tout, ""
    src, n = protect(text)
    tin = tout = 0
    parts = []
    for p in translate.split_for_translation(src, CHUNK) or [src]:
        out, a, b, err = call(client, token, p)
        tin, tout = tin + a, tout + b
        if err:
            return "", tin, tout, err
        parts.append(out)
    fr = restore("\n".join(parts), n)
    if fr is None:
        return "", tin, tout, f"redactions not all returned ({n} sent)"
    return fr, tin, tout, ""


def translate_ruling(client, token: Token, abstract: str, body: str, tries: int = 4) -> dict:
    """The French abstract and body, checked whole, or the reason they are not.

    The abstract is its own request. Sending it ahead of the ruling behind a separator
    line saved a request but lost the separator on 2 rulings in 35; a separate request
    cannot lose anything.
    """
    tin = tout = 0
    last = ""
    # Numbered markers come back whole more often; on the rulings where they do not,
    # the plain form often does. Each attempt is checked the same way, so whichever
    # succeeds is safe to ship.
    for numbered in (True, False, True, False)[:tries]:
        fr_abs, a1, b1, e1 = _translate_text(client, token, abstract, numbered)
        fr_body, a2, b2, e2 = _translate_text(client, token, body, numbered)
        tin, tout = tin + a1 + a2, tout + b1 + b2
        if e1 or e2:
            last = e1 or e2
            continue
        problem = whole(abstract + "\n" + body, fr_abs + "\n" + fr_body)
        if problem:
            last = problem
            continue
        return {"abstract": fr_abs, "body": fr_body, "in": tin, "out": tout, "error": ""}
    return {"abstract": "", "body": "", "in": tin, "out": tout, "error": last}


# ─── Word files ────────────────────────────────────────────────────────────────────

def _rtl(paragraph, run) -> None:
    """Right to left, and bold for the Arabic script too.

    Word keeps a separate bold flag for complex scripts; setting only the ordinary one
    leaves Arabic text looking plain.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    ppr = paragraph._p.get_or_add_pPr()
    if ppr.find(qn("w:bidi")) is None:
        ppr.append(OxmlElement("w:bidi"))
    rpr = run._r.get_or_add_rPr()
    for tag in ("w:rtl",) + (("w:bCs",) if run.bold else ()):
        if rpr.find(qn(tag)) is None:
            rpr.append(OxmlElement(tag))


def arabic_docx(source: Path, target: Path, abstract: str, machine: bool, mark: bool) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    d = Document(str(source))
    first = d.paragraphs[0]._p if d.paragraphs else None
    block = []
    if abstract:
        for text, size in ((TITLE["ar"], TITLE_PT["ar"]), (abstract, ABSTRACT_PT["ar"])):
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            r = p.add_run(text)
            r.bold = True
            _size(r, size, rtl=True)
            _rtl(p, r)
            block.append(p)
        block[0].paragraph_format.space_after = Pt(4)
        block[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        block[1].alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if machine and mark:
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            r = p.add_run(MARK_AR)
            r.italic = True
            r.font.size = Pt(9)
            _rtl(p, r)
            block.append(p)
        block.append(d.add_paragraph())               # a blank line before the ruling
    if first is not None:
        for p in block:
            first.addprevious(p._p)
    target.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(target))


def french_docx(target: Path, abstract: str, body: str, machine: bool, mark: bool) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    d = Document()
    d.styles["Normal"].font.size = Pt(11)
    if abstract:
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(TITLE["fr"])
        r.bold = True
        r.font.size = Pt(TITLE_PT["fr"])
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r = p.add_run(abstract)
        r.bold = True
        r.font.size = Pt(ABSTRACT_PT["fr"])
        if machine and mark:
            r = d.add_paragraph().add_run(MARK_FR)
            r.italic = True
            r.font.size = Pt(9)
        d.add_paragraph()
    for line in body.split("\n"):
        if line.strip():
            d.add_paragraph(line.strip()).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    french_layout(d)
    target.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(target))


# ─── the run ───────────────────────────────────────────────────────────────────────

FIELDS = ["doc_id", "chamber", "abstract", "arabic", "french", "redactions",
          "chars", "tokens_in", "tokens_out", "error"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Write the delivery: abstract on top, and French")
    ap.add_argument("--out", required=True, help="the delivery folder to write")
    ap.add_argument("--results", default=str(_here.parent.parent / "results"),
                    help="the pipeline's results folder, for the file layout")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many rulings")
    ap.add_argument("--workers", type=int, default=64, help="translations in flight")
    ap.add_argument("--arabic-only", action="store_true", help="no translation, no cost")
    ap.add_argument("--no-mark", action="store_true",
                    help="do not mark machine-written abstracts as such")
    ap.add_argument("--sample", action="store_true",
                    help="with --limit, spread the pick across the chambers")
    args = ap.parse_args()

    # Hold off sleep while this runs, on Windows. It is meant to be left alone for an
    # hour, and a laptop that sleeps halfway kills every request in flight. The hold
    # ends with the process; nothing about the machine's settings is changed.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except Exception:
            pass

    out = Path(args.out)
    results = Path(args.results)
    paths = {}
    rec_file = results / "records.json"
    if rec_file.exists():
        for r in json.loads(rec_file.read_text(encoding="utf-8")):
            fp = r.get("file_path") or ""
            paths[r["doc_id"]] = fp[len("documents/"):] if fp.startswith("documents/") else fp

    store = Path(os.getenv("FILESTORE_DIR", "data/files"))
    D = db.Decision
    with db.session() as s:
        rows = s.execute(select(D.doc_id, D.category, D.file_name, D.rule, D.abstract,
                                D.body_text, D.version)
                         .where(D.state == "published").order_by(D.doc_id)).all()
    if args.sample and args.limit:
        by = {}
        for r in rows:
            by.setdefault(r[1], []).append(r)
        random.seed(11)
        rows = [r for rs in by.values() for r in random.sample(rs, min(len(rs), max(1, args.limit // len(by))))]
    if args.limit:
        rows = rows[:args.limit]

    report = out / "report.csv"
    out.mkdir(parents=True, exist_ok=True)
    fresh = not report.exists()
    rep = open(report, "a", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(rep, fieldnames=FIELDS)
    if fresh:
        writer.writeheader()

    todo = []
    skipped = 0
    for doc_id, chamber, file_name, rule, abstract, body, version in rows:
        rel = Path(paths.get(doc_id) or f"{chamber}/{file_name}")
        ar = out / "ar" / rel
        fr = out / "fr" / rel.with_suffix(".fr.docx")
        if (fr.exists() or args.arabic_only) and ar.exists():
            skipped += 1
            continue
        court = (rule or "").strip() if len((rule or "").strip()) > 80 else ""
        summary = court or (abstract or "").strip()
        todo.append({"doc_id": doc_id, "chamber": chamber, "src": store / file_name,
                     "ar": ar, "fr": fr, "summary": summary, "machine": bool(summary and not court),
                     "body": body or "", "version": version or 0})
    print(f"rulings      : {len(rows):,}   already done: {skipped:,}   to do: {len(todo):,}")
    if not args.arabic_only:
        print(f"translation  : {MODEL} via {'AI Studio key, then ' if API_KEY else ''}Vertex "
              f"({len(REGIONS)} regions), {args.workers} in flight")
    mark = not args.no_mark

    import httpx
    token = Token()
    if not args.arabic_only:
        token.get()
    client = httpx.Client(limits=httpx.Limits(max_connections=args.workers + 8))

    stats = {"arabic": 0, "french": 0, "failed": 0, "in": 0, "out": 0}
    started = time.time()

    def finish(job, tr):
        row = {"doc_id": job["doc_id"], "chamber": job["chamber"],
               "abstract": ("model" if job["machine"] else "court") if job["summary"] else "none",
               "arabic": "", "french": "", "redactions": job["body"].count(REDACTION),
               "chars": len(job["body"]), "tokens_in": 0, "tokens_out": 0, "error": ""}
        try:
            if not job["ar"].exists():
                arabic_docx(job["src"], job["ar"], job["summary"], job["machine"], mark)
            row["arabic"] = "yes"
            stats["arabic"] += 1
        except Exception as e:
            row["error"] = f"arabic: {type(e).__name__}: {e}"
        if tr is not None:
            row["tokens_in"], row["tokens_out"] = tr["in"], tr["out"]
            stats["in"] += tr["in"]
            stats["out"] += tr["out"]
            if tr["error"]:
                row["error"] = (row["error"] + "; " if row["error"] else "") + f"french: {tr['error']}"
                stats["failed"] += 1
            else:
                french_docx(job["fr"], tr["abstract"], tr["body"], job["machine"], mark)
                row["french"] = "yes"
                stats["french"] += 1
                try:
                    db.save_translation(job["doc_id"], "fr", tr["body"], MODEL, job["version"])
                except Exception:
                    pass           # the website cache is a bonus, the file is the job
        writer.writerow(row)

    done = 0
    try:
        if args.arabic_only:
            for job in todo:
                finish(job, None)
                done += 1
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                queue = iter(todo)
                running = {}
                for job in queue:
                    running[pool.submit(translate_ruling, client, token,
                                        job["summary"], job["body"])] = job
                    if len(running) >= args.workers * 2:
                        break
                while running:
                    ready, _ = wait(running, return_when=FIRST_COMPLETED)
                    for f in ready:
                        job = running.pop(f)
                        finish(job, f.result())
                        done += 1
                        nxt = next(queue, None)
                        if nxt:
                            running[pool.submit(translate_ruling, client, token,
                                                nxt["summary"], nxt["body"])] = nxt
                        if done % 200 == 0 or done == len(todo):
                            el = time.time() - started
                            cost = stats["in"] / 1e6 * PRICE_IN + stats["out"] / 1e6 * PRICE_OUT
                            rate = done / max(el, 1e-9)
                            print(f"  {done:,}/{len(todo):,}  {rate:.1f}/s  ${cost:.2f}  "
                                  f"failed {stats['failed']}  "
                                  f"~{(len(todo) - done) / max(rate, 1e-9) / 60:.0f} min left",
                                  flush=True)
                            rep.flush()
    finally:
        rep.close()
        client.close()

    el = time.time() - started
    cost = stats["in"] / 1e6 * PRICE_IN + stats["out"] / 1e6 * PRICE_OUT
    print("\n" + "=" * 60)
    print(f"  Arabic files written : {stats['arabic']:,}")
    print(f"  French files written : {stats['french']:,}")
    print(f"  French not shipped   : {stats['failed']:,}   (see report.csv)")
    print(f"  tokens               : {stats['in']:,} in, {stats['out']:,} out")
    print(f"  cost                 : ${cost:.2f}")
    print(f"  time                 : {el / 60:.1f} min")
    print(f"  report               : {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
