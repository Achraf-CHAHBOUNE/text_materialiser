"""Name the subjects and the keyword chains in French, once each.

A subject or a keyword chain repeats across many rulings -- 4,420 subjects and 9,519
distinct chains cover 14,333 rulings -- so each distinct text is translated once and
the answer is written to every ruling that carries it. Rulings already named are
skipped, so this is safe to interrupt and run again.

Texts go in batches as a numbered JSON list and must come back as a list of the same
length; a batch that does not is retried in halves, down to one line at a time.

    python translate_labels.py                  # subjects, then keywords
    python translate_labels.py --only subjects
    python translate_labels.py --limit 40 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    _here = Path(__file__).resolve().parent
except NameError:
    _here = Path.cwd()
sys.path.insert(0, str(_here))
sys.path.insert(0, str(_here.parent / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

import db  # noqa: E402
import deliver  # noqa: E402
from sqlalchemy import select  # noqa: E402

PROMPT = """Tu traduis des intitulés de la jurisprudence de la Cour de cassation du Maroc,
de l'arabe vers le français juridique employé au Maroc (vocabulaire de la Cour de
cassation et des codes marocains : « bail », « immatriculation foncière », « licenciement
abusif », « statut personnel », « pourvoi », etc.).

Règles :
- Traduis chaque élément séparément. Ne fusionne pas, ne coupe pas, n'en saute aucun.
- Garde les tirets « - » qui séparent les mots-clés d'une chaîne, au même endroit.
- Style d'intitulé : court, sans article initial superflu, première lettre en majuscule.
- Laisse XXXXXXX tel quel s'il apparaît.
- Réponds uniquement par une liste JSON de chaînes, dans le même ordre, de même longueur.

Liste à traduire :
"""

BATCH = 40
PRICE_IN, PRICE_OUT = deliver.PRICE_IN, deliver.PRICE_OUT


def _parse(out: str, n: int):
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(got, list) or len(got) != n:
        return None
    got = [str(x).strip() for x in got]
    return got if all(got) else None


def translate_batch(client, token, texts: list, cost: list) -> list:
    """French for each text, in order; "" for any that would not come back."""
    if not texts:
        return []
    out, a, b, err = deliver.call(client, token, json.dumps(texts, ensure_ascii=False),
                                  prompt=PROMPT)
    cost[0] += a
    cost[1] += b
    got = None if err else _parse(out, len(texts))
    if got is not None:
        return got
    if len(texts) == 1:
        return [""]
    mid = len(texts) // 2
    return translate_batch(client, token, texts[:mid], cost) + \
        translate_batch(client, token, texts[mid:], cost)


def run(items: list, workers: int, client, token) -> tuple:
    """{arabic: french} for every item, and what it cost."""
    cost = [0, 0]
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
    done = {}
    lock = threading.Lock()

    def work(batch):
        fr = translate_batch(client, token, batch, cost)
        with lock:
            done.update({a: f for a, f in zip(batch, fr) if f})
            if len(done) // 400 != (len(done) - len(batch)) // 400:
                print(f"  {len(done):,}/{len(items):,}", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, batches))
    return done, cost[0] / 1e6 * PRICE_IN + cost[1] / 1e6 * PRICE_OUT


def subjects(args, client, token) -> None:
    S = db.Subject
    with db.session() as s:
        rows = s.execute(select(S.key, S.label_ar).where(S.label_fr == "")).all()
    labels = sorted({label for _, label in rows if label})
    if args.limit:
        labels = labels[:args.limit]
    print(f"subjects to name: {len(labels):,}")
    fr, usd = run(labels, args.workers, client, token)
    if not args.dry_run:
        with db.session() as s:
            for row in s.scalars(select(S).where(S.label_fr == "")):
                if row.label_ar in fr:
                    row.label_fr, row.model = fr[row.label_ar], deliver.MODEL
            s.commit()
    print(f"subjects named: {len(fr):,}   cost ${usd:.2f}")
    for a in labels[:5]:
        print(f"   {a}  ->  {fr.get(a, '?')}")


def keywords(args, client, token) -> None:
    D, I = db.Decision, db.DecisionI18n
    with db.session() as s:
        named = set(s.scalars(select(I.doc_id).where(I.lang == "fr", I.keywords != "")))
        rows = [(d, k) for d, k in s.execute(
            select(D.doc_id, D.keywords).where(D.state == "published", D.keywords != ""))
            if d not in named]
    chains = sorted({k for _, k in rows})
    if args.limit:
        chains = chains[:args.limit]
    print(f"keyword chains to name: {len(chains):,}  (on {len(rows):,} rulings)")
    fr, usd = run(chains, args.workers, client, token)
    if not args.dry_run:
        by_doc = [(d, fr[k]) for d, k in rows if k in fr]
        for i in range(0, len(by_doc), 500):
            with db.session() as s:
                part = dict(by_doc[i:i + 500])
                have = {r.doc_id: r for r in s.scalars(
                    select(I).where(I.lang == "fr", I.doc_id.in_(list(part))))}
                for doc_id, words in part.items():
                    row = have.get(doc_id)
                    if row is None:
                        row = I(doc_id=doc_id, lang="fr")
                        s.add(row)
                    row.keywords = words
                    row.search_text = db._fold_i18n(row)
                s.commit()
    print(f"keyword chains named: {len(fr):,}   cost ${usd:.2f}")
    for a in chains[:5]:
        print(f"   {a}  ->  {fr.get(a, '?')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Name subjects and keyword chains in French")
    ap.add_argument("--only", choices=["subjects", "keywords"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true", help="translate, write nothing")
    args = ap.parse_args()

    import httpx
    token = deliver.Token()
    client = httpx.Client(limits=httpx.Limits(max_connections=args.workers + 4))
    if args.only in (None, "subjects"):
        subjects(args, client, token)
    if args.only in (None, "keywords"):
        keywords(args, client, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
