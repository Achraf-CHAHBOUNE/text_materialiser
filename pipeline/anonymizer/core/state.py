"""Resume / checkpoint state.

A single JSON file maps each document id to its processing result. On rerun,
documents marked "done" (with their output still present) are skipped.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional


def _replace(src: str, dst: Path, attempts: int = 8) -> None:
    """os.replace, retried while Windows briefly holds the target open.

    A virus scanner or the search indexer opening the state file for a moment makes
    a replace fail with "Access is denied"; the state is saved after every document,
    so over a long run that is near-certain to happen at least once.
    """
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05 * (2 ** i))


@dataclass
class DocRecord:
    status: str  # "done" | "failed" | "duplicate" (a byte-identical copy of another)
    output: str = ""
    category: str = ""   # black-text chamber (the classification)
    court: str = ""      # blue-header court (context)
    pages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    pii_count: int = 0
    unmatched: int = 0
    error: str = ""
    ts: str = ""


class State:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._records: Dict[str, DocRecord] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._records = {k: DocRecord(**v) for k, v in raw.items()}
            except (json.JSONDecodeError, TypeError):
                # Corrupt/old state: start fresh rather than crash.
                self._records = {}

    def _save_unlocked(self) -> None:
        # Atomic write: write to temp file in same dir, then replace.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {k: asdict(v) for k, v in self._records.items()},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            _replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def is_done(self, doc_id: str) -> bool:
        rec = self._records.get(doc_id)
        return rec is not None and rec.status == "done"

    def get(self, doc_id: str) -> Optional[DocRecord]:
        return self._records.get(doc_id)

    def items(self) -> list:
        """(doc_id, record) pairs, a snapshot safe to iterate while updating."""
        with self._lock:
            return list(self._records.items())

    def update(self, doc_id: str, record: DocRecord) -> None:
        with self._lock:
            self._records[doc_id] = record
            self._save_unlocked()

    def export_index(self, path: Path) -> int:
        """Write the side-mission index: file name + category (+ context) for every
        successfully processed document. UTF-8 BOM so Arabic opens cleanly in Excel."""
        done = [(doc_id, r) for doc_id, r in sorted(self._records.items()) if r.status == "done"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["file", "category", "court", "pages", "pii_count"])
            for doc_id, r in done:
                writer.writerow([doc_id, r.category, r.court, r.pages, r.pii_count])
        return len(done)

    def mark_duplicates(self, copies: Dict[str, str]) -> None:
        """Record each {copy: original}, keeping any cost already spent, in one save.

        One save per copy rewrote the whole file ten thousand times for one folder --
        slow, and enough rapid replaces that Windows refused one and the run died.
        """
        if not copies:
            return
        with self._lock:
            for doc_id, original in copies.items():
                rec = self._records.get(doc_id) or DocRecord(status="duplicate")
                rec.status = "duplicate"
                rec.output = ""
                rec.error = f"copy of {original}"
                self._records[doc_id] = rec
            self._save_unlocked()

    def totals(self) -> dict:
        done = [r for r in self._records.values() if r.status == "done"]
        spent = list(self._records.values())
        return {
            "documents": len(done),
            "pages": sum(r.pages for r in done),
            # Tokens and cost count every document actually paid for -- including
            # copies that were processed before duplicates were detected.
            "input_tokens": sum(r.input_tokens for r in spent),
            "output_tokens": sum(r.output_tokens for r in spent),
            "cost": sum(r.cost for r in spent),
            "pii": sum(r.pii_count for r in done),
            "failed": sum(1 for r in self._records.values() if r.status == "failed"),
            "duplicates": sum(1 for r in self._records.values() if r.status == "duplicate"),
        }
