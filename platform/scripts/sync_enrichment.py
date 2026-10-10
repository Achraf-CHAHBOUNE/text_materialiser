"""Move the subjects and summaries between two copies of the database.

They were worked out once, on the machine that had the corpus. Running the classifier
again on the server would cost the same money for the same answers, and would not even
give the same ones, so this carries the computed values across instead.

Only what was derived travels -- subject, its key, where it came from, the written
summary, and the outcome. The ruling's text, its file and anything edited by hand are never touched.

    python sync_enrichment.py export out.jsonl      # from the machine that has them
    python sync_enrichment.py apply out.jsonl       # on the one that needs them
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

try:
    _backend = Path(__file__).resolve().parents[1] / "backend"
except NameError:
    _backend = Path.cwd()
if not (_backend / "db.py").exists():
    _backend = Path.cwd()
sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db  # noqa: E402
from sqlalchemy import or_, select  # noqa: E402

FIELDS = ("theme", "theme_key", "theme_source", "keywords", "rule",
          "abstract", "outcome")


def opener(path: Path, mode: str):
    return gzip.open(path, mode + "t", encoding="utf-8") if path.suffix == ".gz" \
        else open(path, mode, encoding="utf-8")


def export(path: Path) -> int:
    D = db.Decision
    n = 0
    with db.session() as s, opener(path, "w") as f:
        rows = s.execute(
            select(D.doc_id, *(getattr(D, c) for c in FIELDS))
            .where(or_(D.theme != "", D.abstract != "", D.rule != ""))
            .order_by(D.doc_id)).all()
        for r in rows:
            f.write(json.dumps(dict(zip(("doc_id", *FIELDS), r)), ensure_ascii=False) + "\n")
            n += 1
    print(f"exported {n:,} rulings to {path}")
    return 0


def apply(path: Path, batch: int = 500) -> int:
    D = db.Decision
    db.init_db()
    seen = changed = missing = skipped = 0
    with opener(path, "r") as f, db.session() as s:
        for line in f:
            rec = json.loads(line)
            seen += 1
            d = s.get(D, rec["doc_id"])
            if d is None:
                missing += 1
                continue
            if d.edited_at is not None:        # hand edits always win
                skipped += 1
                continue
            touched = False
            for c in FIELDS:
                if getattr(d, c) != rec[c]:
                    setattr(d, c, rec[c])
                    touched = True
            changed += bool(touched)
            if seen % batch == 0:
                s.commit()
                print(f"  {seen:,} read, {changed:,} updated", flush=True)
        s.commit()
    print(f"\nread {seen:,}   updated {changed:,}   "
          f"not in this database {missing:,}   hand-edited, left alone {skipped:,}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Carry subjects and summaries across")
    ap.add_argument("action", choices=["export", "apply"])
    ap.add_argument("path", type=Path)
    args = ap.parse_args()
    return export(args.path) if args.action == "export" else apply(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
