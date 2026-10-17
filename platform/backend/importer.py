"""Bring a delivery of anonymized rulings into the platform -- the one way it is done.

A delivery is what the pipeline hands over: `records.json` and the Word files, either
as a folder (results/) or as a .zip of it. Every way in uses this module:

    the admin's upload            POST /api/admin/import  -> an ImportJob, run here
    a folder on the server        python -m importer /path/to/results
    the full ingest with a model  scripts/ingest.py (this, then the model step)

What a ruling gets, and the rules kept whatever the way in:

  - from the pipeline's record: chamber, numbers, date, city, year, links;
  - from the file itself, read here: the text, the subject and keyword chain the
    court printed, its own rule, and the outcome;
  - a ruling the pipeline held back is not imported;
  - every file is re-scanned by the PII gate before it is stored, whatever the
    pipeline said;
  - a ruling edited by hand on the site is left exactly as edited;
  - importing the same ruling again updates it, never duplicates it.

Reading the Word files is the slow part and pure CPU, so it is spread over worker
processes while this process writes to the database in batches.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Iterator, Optional

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

import db
import extract

LIST_MAX = 200            # rulings named in a report; the counts are always complete


def record_row(rec: dict) -> dict:
    """The listing columns, from what the pipeline recorded."""
    fields = rec.get("fields") or {}

    def fv(label: str) -> str:
        return ((fields.get(label) or {}).get("value") or "")

    category = rec.get("category")
    category = category.get("value", "") if isinstance(category, dict) else (category or "")
    date = fv("تاريخ القرار")
    return {
        "doc_id": rec["doc_id"], "source_file": rec.get("source_file", ""),
        "fmt": rec.get("format", ""), "read_method": rec.get("read_method", ""),
        "category": category or "غير محدد", "level": rec.get("level", ""),
        "court": rec.get("court", "") or ("محكمة النقض" if rec.get("level") == "نقض" else ""),
        "decision_no": fv("رقم القرار"), "file_no": fv("رقم الملف"),
        "decision_date": date, "city": rec.get("city") or fv("المدينة"),
        "year": rec.get("year") or date[-4:], "case_id": rec.get("case_id", ""),
        "pii_removed": (rec.get("pii") or {}).get("removed_count", 0),
        "review": rec.get("review", "ok"),
    }


def held_by_pipeline(rec: dict) -> bool:
    return bool(rec.get("quarantined")) or (rec.get("status") or "done") != "done"


# ---------------- where the files come from ----------------
class Folder:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def records(self) -> list:
        return json.loads((self.root / "records.json").read_text(encoding="utf-8"))

    def locate(self, rec: dict, name: str) -> Optional[str]:
        for rel in (rec.get("file_path"), name):
            if rel and (self.root / rel).is_file():
                return str(self.root / rel)
        return None

    def job(self, where: str) -> tuple:
        return ("path", where)


class Zip:
    def __init__(self, path: Path) -> None:
        self.zf = zipfile.ZipFile(path)
        names = self.zf.namelist()

        def base(n: str) -> str:
            # older Windows zip tools write "results\\documents\\x.docx"; zip wants "/"
            return n.replace(chr(92), "/").rsplit("/", 1)[-1]

        self.rec_name = next((n for n in names if base(n) == "records.json"), "")
        if not self.rec_name:
            raise ValueError("records.json not found in the archive")
        self.by_base = {base(n): n for n in names if not n.replace(chr(92), "/").endswith("/")}

    def records(self) -> list:
        return json.loads(self.zf.read(self.rec_name).decode("utf-8"))

    def locate(self, rec: dict, name: str) -> Optional[str]:
        return self.by_base.get(name)

    def job(self, where: str) -> tuple:
        return ("bytes", self.zf.read(where))


def open_source(path: Path):
    path = Path(path)
    if path.is_dir():
        if not (path / "records.json").exists():
            raise ValueError(f"No records.json in {path}")
        return Folder(path)
    if zipfile.is_zipfile(path):
        return Zip(path)
    raise ValueError("A delivery is a folder or a .zip holding records.json and the Word files")


def _read(job: tuple) -> tuple:
    """In a worker process: everything the file carries. Returns (got, data|None)."""
    doc_id, name, (kind, value) = job
    data = Path(value).read_bytes() if kind == "path" else value
    return doc_id, extract.read(name, data), data


# ---------------- the import ----------------
def run(path: Path, *, publish: bool, actor: str, workers: int = 0, batch: int = 400,
        dry_run: bool = False, store=None,
        progress: Optional[Callable[[dict], None]] = None) -> dict:
    """Import a delivery. Returns the counts, and the rulings refused, by name."""
    if store is None:
        from filestore import get_filestore
        store = get_filestore()
    src = open_source(path)
    counts = {"total_records": 0, "imported": 0, "updated": 0, "kept_edited": 0,
              "held_by_pipeline": 0, "no_file": 0, "gate_quarantined": 0, "unreadable": 0,
              "with_subject": 0, "with_rule": 0, "with_outcome": 0}
    quarantined: list = []          # [{doc_id, findings}]
    rejected: list = []             # [{doc_id, reason}]

    jobs, keep = [], {}
    for rec in src.records():
        counts["total_records"] += 1
        doc_id = rec.get("doc_id")
        if not doc_id:
            continue
        if held_by_pipeline(rec):
            counts["held_by_pipeline"] += 1
            if len(quarantined) < LIST_MAX:
                quarantined.append({"doc_id": doc_id, "findings": ["held by the pipeline"]})
            continue
        name = rec.get("anonymized_file") or f"{doc_id}.docx"
        where = src.locate(rec, name)
        if where is None:
            counts["no_file"] += 1
            if len(rejected) < LIST_MAX:
                rejected.append({"doc_id": doc_id, "reason": "no matching file"})
            continue
        jobs.append((doc_id, name, where))
        keep[doc_id] = (rec, name)

    started, done, pending = time.time(), 0, []

    def flush() -> None:
        if pending and not dry_run:
            ids = [row["doc_id"] for row, *_ in pending]
            with db.session() as s:          # edited on the site: neither row nor file is touched
                edited = set(s.scalars(select(db.Decision.doc_id).where(
                    db.Decision.doc_id.in_(ids), db.Decision.edited_at.is_not(None))))
            for k, v in db.upsert_many([p[:4] for p in pending], publish=publish).items():
                counts[k] = counts.get(k, 0) + v
            for row, _, name, _, data in pending:
                if row["doc_id"] not in edited:
                    store.put(name, data)
        pending.clear()

    def handle(doc_id: str, got, data: bytes) -> None:
        rec, name = keep[doc_id]
        if got.error:
            counts["unreadable"] += 1
            if len(rejected) < LIST_MAX:
                rejected.append({"doc_id": doc_id, "reason": f"unreadable: {got.error[:120]}"})
        elif not got.clean:                       # the gate, whatever the pipeline said
            counts["gate_quarantined"] += 1
            if len(quarantined) < LIST_MAX:
                quarantined.append({"doc_id": doc_id, "findings": list(got.findings[:5])})
        else:
            row = record_row(rec)
            # what the file carries fills or updates a field, and what it does not carry
            # leaves the field alone: a subject a model wrote for a ruling that prints
            # none must survive the same ruling being imported again
            row.update({k: v for k, v in extract.fields(got).items() if v})
            counts["with_subject"] += bool(got.theme)
            counts["with_rule"] += bool(got.rule)
            counts["with_outcome"] += bool(got.outcome)
            pending.append((row, got.text, name, rec.get("links") or [], data))

    def tasks() -> Iterator[tuple]:
        for doc_id, name, where in jobs:
            yield doc_id, name, src.job(where)

    workers = workers or min(8, os.cpu_count() or 4)
    if workers <= 1 or len(jobs) < 20:            # small batches: no processes to start
        results = map(_read, tasks())
        pool = None
    else:
        pool = ProcessPoolExecutor(max_workers=workers)
        results = pool.map(_read, tasks(), chunksize=8)
    try:
        for doc_id, got, data in results:
            done += 1
            handle(doc_id, got, data)
            if len(pending) >= batch:
                flush()
                if progress:
                    progress({**counts, "read": done, "to_read": len(jobs)})
    finally:
        if pool:
            pool.shutdown()
    flush()

    counts["seconds"] = round(time.time() - started, 1)
    if not dry_run:
        db.add_audit(actor, "import", "delivery", Path(path).name,
                     new=", ".join(f"{k}={v}" for k, v in counts.items()))
    return {**counts, "quarantined": quarantined, "rejected": rejected}


# ---------------- an upload, run by the worker ----------------
class ImportJob(db.Base):
    """An uploaded delivery and how its import went."""
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_key: Mapped[str] = mapped_column(String, default="")       # the .zip in the store
    file_name: Mapped[str] = mapped_column(String, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)  # queued|running|done|failed
    result: Mapped[str] = mapped_column(Text, default="")           # JSON: counts and lists
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


def job_dict(j: ImportJob) -> dict:
    result = json.loads(j.result) if j.result else {}
    return {"id": j.id, "file_name": j.file_name, "size": j.size, "status": j.status,
            "error": j.error, "created_by": j.created_by,
            "created_at": j.created_at.isoformat() if j.created_at else "",
            "started_at": j.started_at.isoformat() if j.started_at else "",
            "finished_at": j.finished_at.isoformat() if j.finished_at else "",
            **result}


def _save(job_id: int, **values) -> None:
    with db.session() as s:
        j = s.get(ImportJob, job_id)
        for k, v in values.items():
            setattr(j, k, v)
        s.commit()


def run_job(job_id: int, *, publish: bool, store=None) -> dict:
    """Run one queued upload: fetch its .zip from the store, import it, record how it went."""
    import tempfile
    if store is None:
        from filestore import get_filestore
        store = get_filestore()
    with db.session() as s:
        j = s.get(ImportJob, job_id)
        key, actor = j.file_key, j.created_by
    _save(job_id, status="running", started_at=dt.datetime.utcnow(), error="")
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(store.get(key))
        out = run(Path(tmp), publish=publish, actor=actor, store=store,
                  progress=lambda c: _save(job_id, result=json.dumps(c, ensure_ascii=False)))
        _save(job_id, status="done", finished_at=dt.datetime.utcnow(),
              result=json.dumps(out, ensure_ascii=False))
        store.delete(key)                              # imported: the upload is not kept
    except Exception as e:                             # kept, so it can be run again
        _save(job_id, status="failed", finished_at=dt.datetime.utcnow(), error=f"{type(e).__name__}: {e}"[:2000])
    finally:
        os.unlink(tmp)
    with db.session() as s:
        return job_dict(s.get(ImportJob, job_id))


def run_queued(*, publish: bool) -> int:
    """For the worker: run every upload waiting, oldest first. One worker at a time."""
    with db.exclusive("worker:imports") as mine:
        if not mine:
            return 0
        with db.session() as s:
            # holding the lock, nothing else is running: a 'running' job was cut off
            for j in s.scalars(select(ImportJob).where(ImportJob.status == "running")):
                j.status = "queued"
            s.commit()
            ids = list(s.scalars(select(ImportJob.id).where(ImportJob.status == "queued")
                                 .order_by(ImportJob.id)))
        for job_id in ids:
            run_job(job_id, publish=publish)
        return len(ids)


def main() -> int:
    ap = argparse.ArgumentParser(description="Import a delivery: a results folder or a .zip of it")
    ap.add_argument("path", help="the results folder, or a .zip holding records.json and the files")
    ap.add_argument("--no-publish", action="store_true", help="import for review instead of publishing")
    ap.add_argument("--actor", default="import-script", help="who to record in the audit log")
    ap.add_argument("--workers", type=int, default=0, help="readers (default: cores, max 8)")
    ap.add_argument("--dry-run", action="store_true", help="read and report, write nothing")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    db.init_db()
    out = run(Path(args.path), publish=not args.no_publish, actor=args.actor,
              workers=args.workers, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in out.items() if not isinstance(v, list)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
