"""The Word files' half of a backup: copy the object store to a folder, and back.

    python -m ops.backup save    /backups/20261016-0330      # store -> folder
    python -m ops.backup restore /backups/20261016-0330      # folder -> store

scripts/backup.sh runs `save` beside a pg_dump of the database, so the two halves are
taken together; scripts/restore.sh runs `restore` after putting the database back.

Each backup is a complete folder that needs no other to be restored. A file unchanged
since the previous backup is not copied again but hard-linked to it, so fourteen
nightly backups of 1.2 GB take about 1.2 GB plus what changed. A file is "unchanged"
when its size and checksum match; a corrected ruling keeps its name but not its
checksum, so it is copied.

`restore` makes the store hold exactly the backup: files missing or different are
uploaded, and files the backup does not have are deleted -- the database restored
beside it does not know them.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MANIFEST = "manifest.json"


def _previous(dest: Path) -> Path | None:
    """The newest earlier backup beside this one that finished (it has a manifest)."""
    done = sorted(p for p in dest.parent.iterdir()
                  if p.is_dir() and p != dest and (p / "files" / MANIFEST).exists() and p.name < dest.name)
    return done[-1] if done else None


def save(dest: Path, workers: int = 8) -> dict:
    from filestore import get_filestore
    store = get_filestore()
    files = dest / "files"
    files.mkdir(parents=True, exist_ok=True)
    now = store.listing()
    prev = _previous(dest)
    before = json.loads((prev / "files" / MANIFEST).read_text()) if prev else {}
    linked = copied = 0

    def fetch(name: str) -> None:
        (files / name).write_bytes(store.get(name))

    todo = []
    for name, (size, sum_) in now.items():
        old = before.get(name)
        if old and old == [size, sum_] and (prev / "files" / name).exists():
            try:
                os.link(prev / "files" / name, files / name)
            except OSError:                       # a filesystem without hard links
                shutil.copyfile(prev / "files" / name, files / name)
            linked += 1
        else:
            todo.append(name)
    started = time.time()
    with ThreadPoolExecutor(workers) as pool:
        for _ in pool.map(fetch, todo):
            copied += 1
    # written last: a backup without its manifest is an unfinished one
    (files / MANIFEST).write_text(json.dumps({n: list(v) for n, v in now.items()}))
    out = {"files": len(now), "copied": copied, "linked": linked,
           "bytes": sum(v[0] for v in now.values()), "seconds": round(time.time() - started, 1),
           "since": prev.name if prev else ""}
    print(json.dumps(out))
    return out


def restore(src: Path, workers: int = 8) -> dict:
    from filestore import get_filestore
    store = get_filestore()
    files = src / "files"
    manifest = json.loads((files / MANIFEST).read_text())
    have = store.listing()
    todo = [n for n, v in manifest.items() if list(have.get(n, ())) != v]
    extra = [n for n in have if n not in manifest]

    def put(name: str) -> None:
        store.put_file(name, str(files / name))

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(put, todo))
    for name in extra:
        store.delete(name)
    after = store.sizes()
    wrong = [n for n, (size, _) in manifest.items() if after.get(n) != size]
    if wrong:
        raise SystemExit(f"restore: {len(wrong)} files missing or of another size, e.g. {wrong[:3]}")
    out = {"files": len(manifest), "uploaded": len(todo), "deleted": len(extra)}
    print(json.dumps(out))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["save", "restore"])
    ap.add_argument("folder", help="the backup folder (one per backup)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    (save if a.action == "save" else restore)(Path(a.folder), a.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
