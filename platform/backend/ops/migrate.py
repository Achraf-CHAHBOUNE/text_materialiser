"""Move a platform that ran on SQLite and a folder into Postgres and the object store.

    python -m ops.migrate --sqlite /source/app.db --files /source/files [--replace]

The target is whatever the backend is configured for (DATABASE_URL, S3_*). The
source is only read: the SQLite file is opened read-only, the folder is never
changed, so a failed or interrupted move can simply be run again.

Database: the structure is made by the backend's own db.init_db() (tables, the
Postgres word-search columns and indexes), then every table the models define is
copied in batches, ids included, and each id counter is moved past the highest id.
A target that already holds rows is refused unless --replace is given, which
empties every table first.

Files: every file missing from the store, or there with another size, is uploaded;
the rest are skipped, so an interrupted upload resumes where it stopped. With --replace,
files the source does not have are removed, as the database's rows are.

Both end with a check -- the row count of every table, the name and size of every
file, and the content of a random sample -- and the command fails if anything
differs.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import Integer, create_engine, func, inspect, select, text

BATCH = 1000


def _clean(v):
    # Postgres refuses the NUL character in text; SQLite kept a few from the source files
    return v.replace("\x00", "") if isinstance(v, str) else v


def copy_database(sqlite_path: str, replace: bool) -> None:
    import server  # noqa: F401  -- registers every model on db.Base
    import db

    src = create_engine(f"sqlite:///file:{sqlite_path}?mode=ro&uri=true", future=True)
    dst = db._engine
    if dst.dialect.name != "postgresql":
        raise SystemExit("DATABASE_URL must point at Postgres for this move.")
    db.init_db()
    dst.dispose()                                     # our own idle connections are not "others"
    with dst.connect() as c:                          # nothing else may write meanwhile
        others = c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                "AND pid <> pg_backend_pid()")).scalar()
    if others:
        raise SystemExit(f"{others} other connection(s) to the database: stop the site and the worker "
                         f"first (docker compose stop backend worker), then run this again.")
    tables = db.Base.metadata.sorted_tables          # parents before children
    src_tables = set(inspect(src).get_table_names())

    with dst.begin() as c:
        filled = [t.name for t in tables if c.execute(select(func.count()).select_from(t)).scalar()]
        if filled and not replace:
            raise SystemExit(f"The target already holds rows ({', '.join(filled[:6])}...). "
                             f"Run again with --replace to empty it first.")
        if filled:
            c.execute(text("TRUNCATE " + ", ".join(f'"{t.name}"' for t in tables) + " RESTART IDENTITY CASCADE"))
            print(f"db: emptied {len(tables)} tables")

    expected: dict = {}
    for t in tables:
        if t.name not in src_tables:
            print(f"db: {t.name:28} not in the source, left empty")
            expected[t.name] = 0
            continue
        have = {c["name"] for c in inspect(src).get_columns(t.name)}
        cols = [c for c in t.columns if c.name in have and c.computed is None]
        started, n = time.time(), 0
        with src.connect() as s, dst.begin() as d:
            rows = s.execution_options(yield_per=BATCH).execute(select(*cols))
            for part in rows.partitions(BATCH):
                d.execute(t.insert(), [{c.name: _clean(v) for c, v in zip(cols, r)} for r in part])
                n += len(part)
        expected[t.name] = n
        print(f"db: {t.name:28} {n:>8} rows  {time.time() - started:6.1f}s")

    with dst.begin() as d:                           # new rows must not reuse a copied id
        for t in tables:
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and isinstance(pk[0].type, Integer) and pk[0].autoincrement in (True, "auto"):
                seq = d.execute(text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": t.name, "c": pk[0].name}).scalar()
                if seq:
                    d.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(\"{pk[0].name}\") FROM \"{t.name}\"), 0) + 1, false)"))

    wrong = []
    with dst.connect() as d:
        for t in tables:
            got = d.execute(select(func.count()).select_from(t)).scalar()
            if got != expected[t.name]:
                wrong.append(f"{t.name}: {got} != {expected[t.name]}")
    if wrong:
        raise SystemExit("db: counts differ -- " + "; ".join(wrong))
    print(f"db: checked, {sum(expected.values())} rows in {len(tables)} tables match the source")


def copy_files(folder: str, workers: int, replace: bool = False) -> None:
    from filestore import LocalFileStore, S3FileStore, get_filestore

    local, store = LocalFileStore(folder), get_filestore()
    if not isinstance(store, S3FileStore):
        raise SystemExit("S3_ENDPOINT is not set: there is no object store to copy into.")
    want, have = local.sizes(), store.sizes()
    if replace:                 # the database was emptied too: what it no longer knows goes
        extra = [n for n in have if n not in want]
        for n in extra:
            store.delete(n)
        if extra:
            print(f"files: removed {len(extra)} the source does not have")
        have = {n: v for n, v in have.items() if n in want}
    todo = [n for n, size in want.items() if have.get(n) != size]
    print(f"files: {len(want)} in the folder, {len(want) - len(todo)} already in the store, {len(todo)} to upload")

    def up(name: str) -> None:
        store.put(name, local.get(name))

    started, done = time.time(), 0
    with ThreadPoolExecutor(workers) as pool:
        for f in as_completed([pool.submit(up, n) for n in todo]):
            f.result()
            done += 1
            if done % 2000 == 0 or done == len(todo):
                print(f"files: {done}/{len(todo)}  {time.time() - started:6.0f}s")

    have = store.sizes()
    missing = [n for n, size in want.items() if have.get(n) != size]
    if missing:
        raise SystemExit(f"files: {len(missing)} missing or of another size, e.g. {missing[:3]}")
    sample = random.sample(sorted(want), min(200, len(want)))
    bad = [n for n in sample if store.get(n) != local.get(n)]
    if bad:
        raise SystemExit(f"files: content differs for {bad[:3]}")
    print(f"files: checked, all {len(want)} present with the same size; {len(sample)} compared byte for byte")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sqlite", help="the SQLite database to copy (read-only)")
    p.add_argument("--files", help="the folder of files to copy (read-only)")
    p.add_argument("--replace", action="store_true", help="empty a target database that already holds rows")
    p.add_argument("--workers", type=int, default=8, help="parallel uploads (default 8)")
    a = p.parse_args()
    if not a.sqlite and not a.files:
        p.error("give --sqlite, --files, or both")
    if a.sqlite:
        copy_database(a.sqlite, a.replace)
    if a.files:
        copy_files(a.files, a.workers, a.replace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
