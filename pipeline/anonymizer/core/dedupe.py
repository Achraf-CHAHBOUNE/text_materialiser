"""Find byte-identical copies before paying to process them.

Client folders hold the same ruling under several names ("1976_777_1976-12-15.pdf",
"…_1.pdf", "civile_1976-12-15_1976_777_1e3e9335.pdf"): 42% of one 24,123-file
folder, 37% of another. Processing every copy costs money and shows the same
ruling several times in a listing. Copies are detected by content, never by name --
filenames in these folders are unreliable, and two different rulings can share a
decision number.

Hashes are cached by (path, size, mtime), so a resumed run does not re-read
gigabytes of PDFs.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Tuple


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class HashCache:
    """md5 per file, remembered across runs while the file is unchanged."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: Dict[str, list] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def get(self, path: Path) -> str:
        st = os.stat(path)
        key = str(Path(path).resolve())
        hit = self._data.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
        digest = file_hash(path)
        self._data[key] = [st.st_size, st.st_mtime_ns, digest]
        return digest

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def split_duplicates(
    docs: Iterable,
    hashes: Dict[str, str],
    known: Dict[str, str],
    already_done: Callable[[str], bool],
) -> Tuple[List, Dict[str, str]]:
    """Separate the documents worth processing from the copies.

    `hashes` maps doc_id -> content hash; `known` maps hash -> doc_id for rulings
    already in the case database (possibly from another folder). Returns the
    documents to keep and {copy doc_id: original doc_id}.

    Which copy is the original: one already in the database, else one already
    processed (so nothing is paid for twice), else the first name in sort order --
    a stable choice, so reruns agree.
    """
    groups: Dict[str, List] = {}
    for d in docs:
        groups.setdefault(hashes[d.doc_id], []).append(d)

    keep: List = []
    copies: Dict[str, str] = {}
    for h, members in groups.items():
        ids = {d.doc_id for d in members}
        stored = known.get(h)
        if stored and stored not in ids:
            # The same ruling is already in the database from another folder.
            for d in members:
                copies[d.doc_id] = stored
            continue
        if stored in ids:
            original = stored
        else:
            done = sorted(i for i in ids if already_done(i))
            original = done[0] if done else sorted(ids)[0]
        for d in members:
            if d.doc_id == original:
                keep.append(d)
            else:
                copies[d.doc_id] = original
    keep.sort(key=lambda d: d.doc_id)
    return keep, copies
