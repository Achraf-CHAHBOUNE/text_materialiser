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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class DocRecord:
    status: str  # "done" | "failed"
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
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def is_done(self, doc_id: str) -> bool:
        rec = self._records.get(doc_id)
        return rec is not None and rec.status == "done"

    def get(self, doc_id: str) -> Optional[DocRecord]:
        return self._records.get(doc_id)

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

    def totals(self) -> dict:
        done = [r for r in self._records.values() if r.status == "done"]
        return {
            "documents": len(done),
            "pages": sum(r.pages for r in done),
            "input_tokens": sum(r.input_tokens for r in done),
            "output_tokens": sum(r.output_tokens for r in done),
            "cost": sum(r.cost for r in done),
            "pii": sum(r.pii_count for r in done),
            "failed": sum(1 for r in self._records.values() if r.status == "failed"),
        }
