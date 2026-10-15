"""Write an abstract for every ruling that still has none, and put it into its delivery files.

The summary step only took rulings with no subject at all. A ruling whose court printed
a subject but no rule sentence already had a subject, so it was skipped -- 3,262 of
them reached the delivery with nothing on top. This finds every ruling that has neither
a rule from the court nor a written summary, writes one, and adds it to the top of
both its Word files.

It asks for a summary of what the court decided, not only for a general rule. Many of
the skipped rulings are procedural -- a withdrawal recorded, an appeal out of time --
and lay down no rule, but every ruling decides something.

The French ruling text already in the delivery is kept: only the abstract is
translated, and inserted above it. The court's own subject is never replaced.

    python fill_abstracts.py --delivery ../../delivery
    python fill_abstracts.py --delivery ../../delivery --limit 20 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    _here = Path(__file__).resolve().parent
except NameError:
    _here = Path.cwd()
sys.path.insert(0, str(_here))
_backend = _here.parent / "backend"
if (_backend / "db.py").exists():
    sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db  # noqa: E402
import deliver  # noqa: E402
from sqlalchemy import and_, func, select  # noqa: E402

SUMMARY_PROMPT = """أنت تلخص قرارات محكمة النقض المغربية.

اكتب ملخصا للقرار التالي في جملة إلى ثلاث جمل، بلغة قانونية رصينة:
- إن قرر القرار قاعدة قانونية عامة، فاكتبها بصيغة القواعد.
- وإلا فاذكر ما طُلب من المحكمة وما قضت به وسبب ذلك باختصار.
لا تذكر أسماء الأشخاص ولا الشركات ولا الإدارات ولا المدن ولا أرقام الملفات. اترك
XXXXXXX كما هو إن ورد. لا تضف وقائع ليست في النص.

أجب بالملخص وحده، بلا عنوان ولا شرح.

نص القرار:
"""

# a summary that recites the parties is not one to put in bold on a court file
NAMES = re.compile(r"المسمى|السيد|السيدة|\(.{1,3}\.")


def trim(text: str, head: int = 7000, tail: int = 3000) -> str:
    """The opening and the closing; the middle is argument. Whole if it is short."""
    return text if len(text) <= head + tail else text[:head] + "\n\n[...]\n\n" + text[-tail:]


def summarise(client, token, body: str) -> tuple:
    """(summary, tokens_in, tokens_out, error)."""
    for attempt in range(3):
        out, a, b, err = deliver.call(client, token, trim(body), prompt=SUMMARY_PROMPT)
        if err:
            continue
        out = re.sub(r"\s+", " ", out).strip().strip("«»\"")
        if len(out) < 40:
            err = "too short"
            continue
        if NAMES.search(out):
            err = "named a party"
            continue
        return out, a, b, ""
    return "", 0, 0, err or "failed"


def add_to_french(path: Path, french_abstract: str, mark: bool) -> None:
    """Put the abstract in bold at the top of a French file that already exists."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    d = Document(str(path))
    first = d.paragraphs[0]._p if d.paragraphs else None
    block = []
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(deliver.TITLE["fr"])
    r.bold = True
    r.font.size = Pt(deliver.TITLE_PT["fr"])
    block.append(p)
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(french_abstract)
    r.bold = True
    r.font.size = Pt(deliver.ABSTRACT_PT["fr"])
    block.append(p)
    if mark:
        r = (p2 := d.add_paragraph()).add_run(deliver.MARK_FR)
        r.italic = True
        r.font.size = Pt(9)
        block.append(p2)
    block.append(d.add_paragraph())
    if first is not None:
        for b in block:
            first.addprevious(b._p)
    d.save(str(path))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill in the abstracts the delivery is missing")
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--results", default=str(_here.parent.parent / "results"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--dry-run", action="store_true", help="write the summaries, touch no files")
    ap.add_argument("--no-mark", action="store_true")
    args = ap.parse_args()
    mark = not args.no_mark

    out = Path(args.delivery)
    paths = {}
    rec = Path(args.results) / "records.json"
    if rec.exists():
        for r in json.loads(rec.read_text(encoding="utf-8")):
            fp = r.get("file_path") or ""
            paths[r["doc_id"]] = fp[len("documents/"):] if fp.startswith("documents/") else fp

    store = Path(os.getenv("FILESTORE_DIR", "data/files"))
    D = db.Decision
    with db.session() as s:
        rows = s.execute(select(D.doc_id, D.category, D.file_name, D.body_text)
                         .where(and_(D.state == "published", func.length(D.rule) <= 80,
                                     D.abstract == "")).order_by(D.doc_id)).all()
    if args.limit:
        rows = rows[:args.limit]
    print(f"rulings with no abstract: {len(rows):,}")

    import httpx
    token = deliver.Token()
    client = httpx.Client(limits=httpx.Limits(max_connections=args.workers + 8))
    tin = tout = 0
    lock = threading.Lock()
    stats = {"summary": 0, "arabic": 0, "french": 0, "failed": 0}
    log = open(out / "fill_abstracts.csv", "a", newline="", encoding="utf-8-sig")
    w = csv.writer(log)

    def work(row):
        doc_id, chamber, file_name, body = row
        summ, a, b, err = summarise(client, token, body or "")
        fr_abs = ""
        if summ:
            fr, a2, b2, err2 = deliver._translate_text(client, token, summ, numbered=False)
            a, b = a + a2, b + b2
            fr_abs = fr if not err2 else ""
        return row, summ, fr_abs, a, b, err

    started = time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        for i, (row, summ, fr_abs, a, b, err) in enumerate(pool.map(work, rows), 1):
            doc_id, chamber, file_name, _ = row
            tin, tout = tin + a, tout + b
            if not summ:
                stats["failed"] += 1
                w.writerow([doc_id, "", "", err])
                continue
            stats["summary"] += 1
            if not args.dry_run:
                with db.session() as s:
                    d = s.get(D, doc_id)
                    d.abstract = summ
                    s.commit()
                rel = Path(paths.get(doc_id) or f"{chamber}/{file_name}")
                ar = out / "ar" / rel
                fr = out / "fr" / rel.with_suffix(".fr.docx")
                deliver.arabic_docx(store / file_name, ar, summ, True, mark)   # rebuilt whole
                stats["arabic"] += 1
                if fr_abs and fr.exists():
                    add_to_french(fr, fr_abs, mark)
                    stats["french"] += 1
            w.writerow([doc_id, "yes", "yes" if fr_abs else "", ""])
            if i % 250 == 0:
                print(f"  {i:,}/{len(rows):,}  {i/(time.time()-started):.1f}/s  "
                      f"${tin/1e6*0.10 + tout/1e6*0.40:.2f}", flush=True)
    log.close()
    print(f"\n  summaries written        : {stats['summary']:,}")
    print(f"  Arabic files updated     : {stats['arabic']:,}")
    print(f"  French files updated     : {stats['french']:,}")
    print(f"  still no summary         : {stats['failed']:,}   (fill_abstracts.csv)")
    print(f"  cost                     : ${tin/1e6*0.10 + tout/1e6*0.40:.2f}")
    print(f"  time                     : {(time.time()-started)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
