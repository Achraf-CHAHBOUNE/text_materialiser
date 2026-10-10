"""Re-derive every field we read off a ruling, for rulings already stored.

New columns arrive empty on a database that was imported before they existed, and
re-importing the whole corpus to fill them would also overwrite hand edits. The
headnote is printed in the ruling's own text, and the text is already stored, so this
reads it straight from the database: no files, no pipeline folder, and nothing else
about the ruling is touched.

Rulings that print no headnote - more than half the corpus, mostly civil - keep empty
fields. That is the honest answer for them, not a failure.

The work is paged by primary key rather than streamed. Streaming and committing in one
pass costs Postgres its server-side cursor ("cursor does not exist") the moment the
first batch is written; paging holds no cursor open across a commit, and keeps the
whole corpus from being read into memory at once.

    python backfill_themes.py              # fill the ones still empty
    python backfill_themes.py --all        # re-read every ruling
    python backfill_themes.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Run from platform/scripts, or inside the backend image, where the modules sit in the
# working directory and the script may arrive on stdin with no __file__ at all.
try:
    _backend = Path(__file__).resolve().parents[1] / "backend"
except NameError:
    _backend = Path.cwd()
if not (_backend / "db.py").exists():
    _backend = Path.cwd()
sys.path.insert(0, str(_backend))

import db            # noqa: E402
import extract       # noqa: E402
import headnotes     # noqa: E402
from sqlalchemy import select  # noqa: E402


def derive(text: str) -> dict:
    """Everything a stored ruling's text still has to tell us.

    The same reading `ingest` does on a fresh delivery, minus the parts that need the
    file: there is no PII gate here because the text in the database already passed it,
    and no Word document to store. Kept in step with ingest by calling the same module.
    """
    note = headnotes.read(text or "")
    chain = []
    if note:
        chain = [note.theme, *note.sub] + ([note.qualifier] if note.qualifier else [])
    return {
        "theme": note.theme if note else "",
        "theme_key": headnotes.normalise(note.theme) if note else "",
        "theme_source": "court" if note else "",
        "keywords": " - ".join(chain),
        "rule": note.rule if note else "",
        "outcome": extract.outcome(text or ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill theme and rule from stored text")
    ap.add_argument("--all", action="store_true", help="re-read every ruling")
    ap.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args()

    db.init_db()
    found = seen = outcomes = 0
    started = time.time()
    after = ""
    while True:
        with db.session() as s:
            q = select(db.Decision).where(db.Decision.doc_id > after)
            if not args.all:
                q = q.where(db.Decision.outcome == "")
            rows = s.scalars(q.order_by(db.Decision.doc_id).limit(args.batch)).all()
            if not rows:
                break
            for d in rows:
                seen += 1
                got = derive(d.body_text or "")
                if got["theme"]:
                    found += 1
                if got["outcome"]:
                    outcomes += 1
                if not args.dry_run:
                    for k, v in got.items():
                        # a subject a model wrote is not replaced by "no subject"
                        if k in ("theme", "theme_key", "theme_source", "keywords")                                 and not v and d.theme_source == "model":
                            continue
                        setattr(d, k, v)
            after = rows[-1].doc_id
            if not args.dry_run:
                s.commit()
        print(f"  {seen:,} read, {found:,} with a subject", flush=True)

    print(f"\nread {seen:,} rulings in {time.time() - started:.0f}s")
    print(f"  carry a subject : {found:,} ({found / max(1, seen) * 100:.0f}%)")
    print(f"  carry an outcome: {outcomes:,} ({outcomes / max(1, seen) * 100:.0f}%)")
    print(f"  print none      : {seen - found:,}")
    if args.dry_run:
        print("  (dry run: nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
