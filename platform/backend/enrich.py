"""Give a subject and a summary to the rulings that print neither.

More than half the corpus carries no headnote, so no parsing will ever give those
rulings a subject or an abstract. This asks a model for both. Three rules keep that
from damaging what the court actually wrote:

  - The model never writes over the court. Its summary goes to `abstract`; the court's
    own rule stays in `rule`, untouched, and the page labels which is which.
  - The vocabulary is closed, and the check is ours. Each request carries the subjects
    that chamber already uses, and an answer is accepted only if it is one of them --
    verified here, not taken on the model's word. A pilot showed why: it reported all
    24 of its answers as coming from the list, and two had not.
  - A subject it invents is not silently adopted. It goes to a proposals file for a
    person to approve, and that ruling keeps its abstract but gets no subject.

Work is spread over threads because each call waits on the network: one at a time
would take seven hours. Progress is committed in batches and the run skips what is
already done, so an interruption costs only the batch in flight.

    python -m enrich --limit 100        # a sample first
    python -m enrich                    # the rest
    python -m enrich --dry-run --limit 20

The worker runs it too, after each import, when AUTO_ENRICH=1: then only the rulings
never put to the model are asked (decisions.enriched_at), so each is paid for once.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from pathlib import Path

from sqlalchemy import and_, func, select, update

import clock
import db
import headnotes
import settings

# Three gateways, one job, two request shapes between them. `style` is what actually
# differs: Gemini has its own, everyone else speaks OpenAI's.
#
# Gemini is the default because it is the one measured on this corpus -- 16,585
# rulings, 8 failures, $4.85 -- and because court rulings should go to a provider you
# can name and hold to terms.
PROVIDERS = {
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "model": "gemini-2.5-flash-lite",
        "env": ("TRANSLATE_API_KEY", "GEMINI_API_KEY"),
        "style": "gemini",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "google/gemini-2.5-flash-lite",
        "env": ("OPENROUTER_API_KEY",),
        "style": "openai",
    },
    # OpenCode Zen. Its model ids ending in -free, space-bunny-free among them, are
    # reserved for the OpenCode terminal app and answer 403 to anything else; see
    # FREE_TIER_LOCKED below. The paid ids work normally.
    "opencode": {
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "model": "gemini-3.5-flash-lite",
        "env": ("OPENCODE_API_KEY",),
        "style": "openai",
    },
}

# What OpenCode answers when a -free model is called from outside its own client. Worth
# recognising by name: the message is clear but a run would otherwise report it as an
# anonymous 403 on every single ruling.
FREE_TIER_LOCKED = "free tier can only be used from within"

HEAD, TAIL = 7000, 3000          # the facts and the grounds, then what was decided
MIN_ABSTRACT = 60                # shorter than this is a fragment, not a rule

PROMPT = """أنت تفهرس قرارات محكمة النقض المغربية.

الغرفة: {chamber}

المواضيع المستعملة في هذه الغرفة:
{vocab}

المطلوب، اعتمادا على نص القرار وحده:
1. "theme": الموضوع الأنسب من القائمة أعلاه، منقولا بنفس صيغته بالضبط.
   إن لم يكن في القائمة ما يناسب القرار فعلا، اقترح موضوعا جديدا من كلمتين إلى أربع
   كلمات، اسما لا جملة، على نمط القائمة. لا تختر موضوعا من القائمة لمجرد ملء الحقل.
2. "abstract": القاعدة القانونية التي قررتها المحكمة، في جملة إلى ثلاث جمل، بصيغة
   المحاكم كما تحرر القواعد. لا تذكر أسماء الأطراف ولا الإدارات ولا المدن ولا أرقام
   الملفات. إن لم يقرر القرار قاعدة عامة فاترك الحقل فارغا "".

لا تضف وقائع ليست في النص. أجب بـ JSON صالح فقط، بدون أي شرح."""

# Wording that means the summary recited this case instead of stating a rule.
NAMES = re.compile(r"وزارة|عمالة|مندوب|المسمى|السيد|السيدة|\(.{1,3}\.")


def trim(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(text) <= HEAD + TAIL:
        return text
    return text[:HEAD] + "\n\n[...]\n\n" + text[-TAIL:]


class Budget:
    """Token tally shared across threads."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tin = self.tout = self.calls = self.failed = 0

    def add(self, usage: dict, ok: bool) -> None:
        with self.lock:
            self.tin += usage.get("promptTokenCount", 0)
            self.tout += usage.get("candidatesTokenCount", 0)
            self.calls += 1
            self.failed += 0 if ok else 1

    @property
    def cost(self) -> float:                      # Flash-Lite list price
        return self.tin / 1e6 * 0.10 + self.tout / 1e6 * 0.40


def _request(provider, model, prompt):
    """The one request, in whichever shape the provider expects."""
    if PROVIDERS[provider]["style"] == "gemini":
        return PROVIDERS[provider]["url"].format(model=model), {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048,
                                 "responseMimeType": "application/json"}}
    return PROVIDERS[provider]["url"], {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"}}


def _answer(provider, data):
    """The reply text and what it cost, however the provider reports them."""
    if PROVIDERS[provider]["style"] == "gemini":
        u = data.get("usageMetadata") or {}
        tokens = (u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0))
        cands = data.get("candidates") or []
        if not cands:
            return "", tokens
        parts = (cands[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts).strip(), tokens
    u = data.get("usage") or {}
    tokens = (u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
    choices = data.get("choices") or []
    if not choices:
        return "", tokens
    return ((choices[0].get("message") or {}).get("content") or "").strip(), tokens


def ask(client, text, chamber, vocab, *, key, model, budget, provider="gemini"):
    prompt = (PROMPT.format(chamber=chamber, vocab="\n".join("- " + v for v in vocab))
              + "\n\nنص القرار:\n" + trim(text))
    url, body = _request(provider, model, prompt)
    gemini = PROVIDERS[provider]["style"] == "gemini"
    params = {"key": key} if gemini else {}
    headers = {} if gemini else {"Authorization": f"Bearer {key}"}
    for attempt in range(4):
        try:
            r = client.post(url, params=params, headers=headers, json=body,
                            timeout=120.0)
        except Exception as e:                    # a network blip is worth another go
            if attempt == 3:
                budget.add({}, False)
                return None, type(e).__name__
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            if attempt == 3:
                budget.add({}, False)
                return None, "HTTP " + str(r.status_code)
            time.sleep(2 ** attempt + random.random())
            continue
        if r.status_code == 403 and FREE_TIER_LOCKED in r.text:
            budget.add({}, False)
            return None, "FREE_TIER_LOCKED"
        if r.status_code >= 400:
            budget.add({}, False)
            return None, "HTTP " + str(r.status_code)
        data = r.json()
        out, (tin, tout) = _answer(provider, data)
        budget.add({"promptTokenCount": tin, "candidatesTokenCount": tout}, True)
        if not out:
            return None, "no answer"
        try:
            got = json.loads(out)
        except json.JSONDecodeError:
            return None, "not JSON"
        # Asking for one object sometimes gets a list holding it back instead.
        if isinstance(got, list):
            got = next((x for x in got if isinstance(x, dict)), None)
        if not isinstance(got, dict):
            return None, "not an object"
        return got, None
    return None, "gave up"


def key_for(provider: str) -> str:
    return next((os.getenv(v) for v in PROVIDERS[provider]["env"] if os.getenv(v)), "")


def run(*, limit: int = 0, workers: int = 8, batch: int = 100, vocab_size: int = 60,
        provider: str = "", model: str = "", dry_run: bool = False, only_new: bool = False,
        quiet: bool = False) -> dict:
    """Ask the model for the rulings that print no subject. only_new: just those never
    asked before (the worker's way); otherwise every one still without a summary."""
    provider = provider or os.getenv("LLM_PROVIDER", "gemini")
    spec = PROVIDERS[provider]
    model = model or os.getenv("LLM_MODEL") or spec["model"]
    key = key_for(provider)
    if not key:
        raise RuntimeError(f"no API key for {provider}: set " + " or ".join(spec["env"]))
    say = (lambda *a, **k: None) if quiet else print

    import httpx
    D = db.Decision
    args = argparse.Namespace(limit=limit, workers=workers, batch=batch, vocab=vocab_size,
                              provider=provider, model=model, dry_run=dry_run)

    chambers = ["مدنية", "جنائية", "إدارية", "أحوال شخصية", "تجارية", "اجتماعية", "عقارية"]
    vocab = {c: [t["label"] for t in db.browse_themes(c)[:args.vocab]] for c in chambers}
    allowed = {c: {headnotes.normalise(v): v for v in vs} for c, vs in vocab.items()}

    with db.session() as s:
        q = select(D.doc_id).where(and_(D.state == "published", D.theme == "",
                                        D.abstract == "", func.length(D.body_text) > 800))
        if only_new:
            q = q.where(D.enriched_at.is_(None))
        todo = s.execute(q.order_by(D.doc_id)).scalars().all()
    if args.limit:
        todo = todo[:args.limit]
    say("to classify : {:,}".format(len(todo)))
    say("provider    : {} / {}   workers: {}".format(args.provider, model, args.workers))

    budget = Budget()
    proposals: list = []
    stats = {"subject": 0, "proposed": 0, "abstract": 0, "no_rule": 0,
             "failed": 0, "named": 0, "locked": 0}
    started = time.time()
    done = 0

    client = httpx.Client(limits=httpx.Limits(max_connections=args.workers + 4))
    try:
        for start in range(0, len(todo), args.batch):
            chunk = todo[start:start + args.batch]
            with db.session() as s:
                rows = s.execute(select(D.doc_id, D.category, D.body_text)
                                 .where(D.doc_id.in_(chunk))).all()
                jobs = {r[0]: (r[1], r[2]) for r in rows}

                def work(doc_id):
                    chamber, body = jobs[doc_id]
                    got, err = ask(client, body, chamber, vocab.get(chamber, []),
                                   key=key, model=model, budget=budget,
                                   provider=args.provider)
                    return doc_id, chamber, got, err

                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    results = list(pool.map(work, chunk))

                for doc_id, chamber, got, err in results:
                    done += 1
                    if err == "FREE_TIER_LOCKED":
                        stats["locked"] += 1
                        continue
                    if err:
                        stats["failed"] += 1
                        continue
                    theme = (got.get("theme") or "").strip()
                    abstract = (got.get("abstract") or "").strip()

                    # our check, not the model's claim
                    match = allowed.get(chamber, {}).get(headnotes.normalise(theme))
                    if theme and not match:
                        proposals.append({"doc_id": doc_id, "chamber": chamber,
                                          "proposed": theme})
                        stats["proposed"] += 1

                    if abstract and len(abstract) < MIN_ABSTRACT:
                        abstract = ""
                    if abstract and NAMES.search(abstract):
                        stats["named"] += 1
                        abstract = ""
                    if not abstract:
                        stats["no_rule"] += 1

                    if args.dry_run:
                        continue
                    d = s.get(D, doc_id)
                    if match:
                        d.theme = match
                        d.theme_key = headnotes.normalise(match)
                        d.theme_source = "model"
                        stats["subject"] += 1
                    if abstract:
                        d.abstract = abstract
                        stats["abstract"] += 1
                if not args.dry_run:
                    # asked, whatever came back: never paid for twice by the worker
                    s.execute(update(D).where(D.doc_id.in_(chunk)).values(enriched_at=clock.utcnow()))
                    s.commit()

            if stats["locked"] and stats["locked"] == done:
                say(f"\n  {model} refused every request. OpenCode reserves its -free"
                      "\n  models for the OpenCode app itself, so they cannot be called"
                      "\n  from a script. Choose a paid model id, or another provider.",
                      flush=True)
                break
            rate = done / max(1e-9, time.time() - started)
            left = (len(todo) - done) / max(1e-9, rate) / 60
            say("  {:,}/{:,}  {:.1f}/s  ${:.3f}  ~{:.0f} min left".format(
                done, len(todo), rate, budget.cost, left), flush=True)
    finally:
        client.close()

    if proposals and not args.dry_run:
        out = Path(settings.S.db_dir)
        out.mkdir(parents=True, exist_ok=True)
        f = out / "proposed_subjects.json"
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        f.write_text(json.dumps(old + proposals, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        say("\n  {:,} proposed subjects written to {}".format(len(proposals), f))

    stats.update(processed=done, minutes=round((time.time() - started) / 60, 1),
                 tokens_in=budget.tin, tokens_out=budget.tout, cost=round(budget.cost, 4))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Give a subject and a summary to the rulings with no headnote")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=100, help="rulings per commit")
    ap.add_argument("--vocab", type=int, default=60)
    ap.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "gemini"), choices=sorted(PROVIDERS))
    ap.add_argument("--model", default="", help="override the provider's default")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not key_for(args.provider):
        print(f"no API key for {args.provider}: set " + " or ".join(PROVIDERS[args.provider]["env"]),
              file=sys.stderr)
        return 2
    db.init_db()
    st = run(limit=args.limit, workers=args.workers, batch=args.batch, vocab_size=args.vocab,
             provider=args.provider, model=args.model, dry_run=args.dry_run)
    print("\n" + "=" * 58)
    print("  processed             : {:,} in {} min".format(st["processed"], st["minutes"]))
    print("  subject written       : {:,}".format(st["subject"]))
    print("  subject proposed      : {:,}  (held for approval)".format(st["proposed"]))
    print("  abstract written      : {:,}".format(st["abstract"]))
    print("  no general rule       : {:,}".format(st["no_rule"]))
    print("  dropped, named a party: {:,}".format(st["named"]))
    print("  failed calls          : {:,}".format(st["failed"]))
    if st["locked"]:
        print("  refused, free tier    : {:,}".format(st["locked"]))
    print("  tokens                : {:,} in, {:,} out".format(st["tokens_in"], st["tokens_out"]))
    print("  cost                  : ${:.3f}".format(st["cost"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
