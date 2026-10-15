"""Bring the French already produced into the database the bilingual site reads.

Three things, each skipped if already done, so this is safe to run again:

  1. the French ruling texts, from the old `translations` table into `decision_i18n`
  2. the French abstracts, read from the top of each delivered French Word file
     (deliver.py wrote them there and nowhere else)
  3. the subjects list, one row per subject key with the court's commonest spelling,
     ready for translate_labels.py to name in French

Nothing is translated here and nothing is paid for.

    python migrate_i18n.py --delivery ../../delivery
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

try:
    _here = Path(__file__).resolve().parent
except NameError:
    _here = Path.cwd()
sys.path.insert(0, str(_here.parent / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

import db  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

TITLE_FR = "Résumé de l'arrêt"


def copy_translations(batch: int = 500) -> int:
    """The old table's texts, into decision_i18n, for rulings that have none there."""
    T, I = db.Translation, db.DecisionI18n
    with db.session() as s:
        have = set(s.scalars(select(I.doc_id).where(I.lang == "fr", I.body_text != "")))
        ids = [r for r in s.scalars(select(T.id).where(T.lang == "fr", T.text != ""))]
    n = 0
    for i in range(0, len(ids), batch):
        with db.session() as s:
            for t in s.scalars(select(T).where(T.id.in_(ids[i:i + batch]))):
                if t.doc_id in have:
                    continue
                row = s.scalar(select(I).where(I.doc_id == t.doc_id, I.lang == "fr"))
                if row is None:
                    row = I(doc_id=t.doc_id, lang="fr")
                    s.add(row)
                row.body_text, row.model, row.source_version = t.text, t.model, t.source_version
                row.search_text = db._fold_i18n(row)
                n += 1
            s.commit()
    return n


def read_abstract(path: str) -> str:
    """The abstract under the title at the top of a delivered French file, or ""."""
    from docx import Document
    try:
        paras = Document(path).paragraphs
    except Exception:
        return ""
    if len(paras) > 1 and paras[0].text.strip() == TITLE_FR:
        return paras[1].text.strip()
    return ""


def copy_abstracts(delivery: Path, results: Path, workers: int) -> int:
    paths = {}
    rec = results / "records.json"
    for r in json.loads(rec.read_text(encoding="utf-8")):
        fp = r.get("file_path") or ""
        rel = Path(fp[len("documents/"):] if fp.startswith("documents/") else fp)
        paths[r["doc_id"]] = delivery / "fr" / rel.with_suffix(".fr.docx")
    D, I = db.Decision, db.DecisionI18n
    with db.session() as s:
        done = set(s.scalars(select(I.doc_id).where(I.lang == "fr", I.abstract != "")))
        rows = s.execute(select(D.doc_id, D.rule).where(D.state == "published")).all()
    todo = [(d, rule) for d, rule in rows if d not in done and d in paths and paths[d].exists()]
    print(f"  French files to read: {len(todo):,}")
    with ProcessPoolExecutor(workers) as pool:
        found = list(pool.map(read_abstract, [str(paths[d]) for d, _ in todo], chunksize=64))
    n = 0
    for (doc_id, rule), abstract in zip(todo, found):
        if not abstract:
            continue
        # deliver.py put the court's rule on top when it had one over 80 characters,
        # and the written summary otherwise -- the label has to say which
        of = "rule" if len((rule or "").strip()) > 80 else "abstract"
        db.save_i18n(doc_id, "fr", abstract=abstract, abstract_of=of)
        n += 1
    return n


def build_subjects() -> int:
    D, S = db.Decision, db.Subject
    with db.session() as s:
        rows = s.execute(select(D.theme_key, D.theme, func.count())
                         .where(D.theme_key != "").group_by(D.theme_key, D.theme)).all()
        have = set(s.scalars(select(S.key)))
        best: dict = {}
        for key, label, n in rows:
            if n > best.get(key, ("", 0))[1]:
                best[key] = (label, n)
        new = 0
        for key, (label, _) in best.items():
            if key not in have:
                s.add(S(key=key, label_ar=label))
                new += 1
        s.commit()
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description="Move the French already made into the database")
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--results", default=str(_here.parent.parent / "results"))
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    db.init_db()
    print(f"French texts copied      : {copy_translations():,}")
    print(f"French abstracts read    : {copy_abstracts(Path(args.delivery), Path(args.results), args.workers):,}")
    print(f"subjects added           : {build_subjects():,}")
    I = db.DecisionI18n
    with db.session() as s:
        c = Counter()
        for body, abstract in s.execute(select(func.length(I.body_text), func.length(I.abstract))
                                        .where(I.lang == "fr")):
            c["text"] += bool(body)
            c["abstract"] += bool(abstract)
    print(f"now in French            : {c['text']:,} texts, {c['abstract']:,} abstracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
