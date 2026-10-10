"""Add the word-search column to a database that is already serving.

Searching used `search_text LIKE '%word%'`. The trigram index answered that in 8 ms,
but LIKE is lossy, so Postgres had to fetch and decompress every candidate ruling to
recheck it -- 11,544 of them, 3.4 seconds on a common word. A tsvector needs no
recheck.

Indexing `to_tsvector(...)` as an expression is not enough: whenever the planner chose
to walk the sort order and filter rather than use the index, it recomputed the vector
over a 15 KB ruling for every row it looked at, which was slower than what it replaced.
The vector has to be stored.

The obvious way to store it, a GENERATED ... STORED column, rewrites the whole table
under an exclusive lock. On a live site that is an outage, and on a database limited to
a fraction of a core it is a long one. So instead:

  - add the column empty, which only touches the catalog;
  - fill it in batches, each its own short transaction;
  - index it CONCURRENTLY, which never blocks readers or writers;
  - and keep it current with a trigger, so it does not matter which code writes a row.

Safe to interrupt and safe to run again: it only ever fills rows that are still empty.

    python migrate_search_tsv.py            # against DATABASE_URL
    python migrate_search_tsv.py --batch 1000
"""
from __future__ import annotations

import argparse
import sys
import time
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
from sqlalchemy import text  # noqa: E402

TRIGGER = """
CREATE OR REPLACE FUNCTION decisions_tsv_refresh() RETURNS trigger AS $fn$
BEGIN
    NEW.search_tsv := to_tsvector('simple', coalesce(NEW.search_text, ''));
    RETURN NEW;
END
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decisions_tsv ON decisions;
CREATE TRIGGER trg_decisions_tsv
    BEFORE INSERT OR UPDATE OF search_text ON decisions
    FOR EACH ROW EXECUTE FUNCTION decisions_tsv_refresh();
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Add and fill the search_tsv column")
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args()

    if db._engine.dialect.name != "postgresql":
        print("nothing to do: this only applies to Postgres")
        return 0

    started = time.time()
    with db._engine.begin() as c:
        c.execute(text("ALTER TABLE decisions ADD COLUMN IF NOT EXISTS search_tsv tsvector"))
    print("column added (catalog only, no lock held)")

    with db._engine.begin() as c:
        c.execute(text(TRIGGER))
    print("trigger installed: new and edited rulings keep themselves current")

    done = 0
    while True:
        with db._engine.begin() as c:
            n = c.execute(text(
                "UPDATE decisions SET search_tsv = to_tsvector('simple', coalesce(search_text,'')) "
                "WHERE doc_id IN (SELECT doc_id FROM decisions WHERE search_tsv IS NULL "
                "                 ORDER BY doc_id LIMIT :n)"), {"n": args.batch}).rowcount
        if not n:
            break
        done += n
        rate = done / max(1e-9, time.time() - started)
        print(f"  filled {done:,}   {rate:.0f}/s", flush=True)

    print(f"filled {done:,} rulings in {time.time()-started:.0f}s")

    # CONCURRENTLY cannot run inside a transaction block
    raw = db._engine.raw_connection()
    try:
        raw.set_session(autocommit=True) if hasattr(raw, "set_session") else None
        raw.autocommit = True
        cur = raw.cursor()
        print("building the index concurrently (readers and writers carry on)...")
        cur.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dec_tsv_col "
                    "ON decisions USING gin (search_tsv)")
        cur.execute("ANALYZE decisions")
        cur.close()
    finally:
        raw.close()
    print(f"done in {time.time()-started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
