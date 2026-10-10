"""Load a pipeline `results/` folder into the platform, locally.

The HTTP import takes a .zip, which means uploading hundreds of megabytes through
the browser; for a full corpus that is slow and pointless when the folder is on the
same machine. This reads the folder directly and applies exactly the same rules as
the HTTP import:

  - a record the pipeline held back is never imported;
  - every file is re-scanned by the PII gate before it is stored;
  - re-importing the same ruling updates it instead of duplicating it;
  - a ruling edited by hand on the site is left exactly as edited.

Reading 29,384 Word files is the slow part, and it is pure CPU: each one is a zip
holding XML. So the reading is spread over worker processes while the main process
writes to the database in batches. One thread doing everything managed about 25
rulings a second; this does several times that.

    python import_results.py ../../results            # import and publish
    python import_results.py ../../results --no-publish
    python import_results.py ../../results --workers 4
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import db
import headnotes
import piigate
import textextract
from filestore import LocalFileStore, get_filestore

STORE = get_filestore()


def _row(rec: dict) -> dict:
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
        "outcome": rec.get("outcome", ""),
        "pii_removed": (rec.get("pii") or {}).get("removed_count", 0),
        "review": rec.get("review", "ok"),
    }


def _headnote_fields(note) -> dict:
    """The court's own subject line, as four columns.

    `keywords` is the chain written back the way the court writes it, dashes and all,
    because that is what the portal shows and what a reader recognises. A ruling that
    printed no headnote gets empty strings, not a guess.
    """
    if not note:
        return {"theme": "", "theme_key": "", "keywords": "", "rule": ""}
    chain = [note.theme, *note.sub] + ([note.qualifier] if note.qualifier else [])
    return {"theme": note.theme, "theme_key": headnotes.normalise(note.theme),
            "keywords": " - ".join(chain), "rule": note.rule}


def read_and_check(job: tuple) -> tuple:
    """In a worker process: read the file, pull out its text, run the PII gate, and
    take the headnote the court printed on it.

    Returns (doc_id, text, headnote, clean, error). Only text travels back, never the
    file: the main process copies that from disk, which costs nothing. Reading the
    headnote here rather than later costs nothing either -- the text is already in hand
    and the worker is the process with time to spare.
    """
    doc_id, path, name = job
    try:
        text = textextract.extract(name, Path(path).read_bytes())
    except Exception as e:                       # a damaged file must not stop the run
        return doc_id, "", None, False, f"{type(e).__name__}: {e}"
    return doc_id, text, headnotes.read(text), not piigate.scan(text), None


def _store(name: str, path: Path) -> None:
    """Put the file in the store, copying rather than reading it into memory."""
    if isinstance(STORE, LocalFileStore):
        STORE.base.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, STORE.base / name)
    else:
        STORE.put(name, path.read_bytes())


def import_folder(results: Path, publish: bool, actor: str, workers: int = 0) -> dict:
    records = json.loads((results / "records.json").read_text(encoding="utf-8"))
    counts = {"imported": 0, "updated": 0, "held_by_pipeline": 0, "no_file": 0,
              "gate_quarantined": 0, "kept_edited": 0, "unreadable": 0, "with_theme": 0}

    jobs, keep = [], {}
    for rec in records:
        if rec.get("quarantined") or rec.get("status") != "done":
            counts["held_by_pipeline"] += 1
            continue
        name = rec.get("anonymized_file") or f"{rec['doc_id']}.docx"
        path = results / (rec.get("file_path") or name)
        if not path.exists():
            counts["no_file"] += 1
            continue
        jobs.append((rec["doc_id"], str(path), name))
        keep[rec["doc_id"]] = (rec, name, path)

    workers = workers or min(8, (os.cpu_count() or 4))
    started, done = time.time(), 0
    pending: list = []

    def flush() -> None:
        if not pending:
            return
        got = db.upsert_many(pending, publish=publish)
        for k, v in got.items():
            counts[k] = counts.get(k, 0) + v
        pending.clear()

    print(f"  reading {len(jobs):,} files with {workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for doc_id, text, note, clean, err in pool.map(read_and_check, jobs, chunksize=16):
            done += 1
            rec, name, path = keep[doc_id]
            if err:
                counts["unreadable"] += 1
            elif not clean:                       # the gate: same rule as the HTTP import
                counts["gate_quarantined"] += 1
            else:
                row = _row(rec)
                row.update(_headnote_fields(note))
                if note:
                    counts["with_theme"] += 1
                pending.append((row, text, name, rec.get("links") or []))
                _store(name, path)
            if len(pending) >= 400:
                flush()
            if done % 2000 == 0:
                rate = done / max(1e-9, time.time() - started)
                print(f"  {done:,}/{len(jobs):,}  ({rate:.0f}/s)", flush=True)
    flush()

    db.add_audit(actor, "import", "folder", str(results),
                 new=", ".join(f"{k}={v}" for k, v in counts.items()))
    counts["seconds"] = round(time.time() - started, 1)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Import a pipeline results folder")
    ap.add_argument("results", help="the results folder (with records.json)")
    ap.add_argument("--no-publish", action="store_true", help="import for review instead")
    ap.add_argument("--actor", default="import-script", help="who to record in the audit log")
    ap.add_argument("--workers", type=int, default=0, help="readers (default: cores, max 8)")
    args = ap.parse_args()

    results = Path(args.results)
    if not (results / "records.json").exists():
        print(f"No records.json in {results}", file=sys.stderr)
        return 2
    db.init_db()
    counts = import_folder(results, publish=not args.no_publish, actor=args.actor,
                           workers=args.workers)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(json.dumps(db.counts(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
