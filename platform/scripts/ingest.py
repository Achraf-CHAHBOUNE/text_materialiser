"""Take a delivery of anonymized rulings and make it searchable. One command.

This replaces four passes that each re-read the same files: import the folder, read
the headnotes, ask a model for the ones with none, fold the proposals back in. Now a
ruling is opened once, in a worker process, and everything that can be read off it is
read at once; only the rulings that print nothing go to a model afterwards.

    python ingest.py ../../results
    python ingest.py ../../results --no-model          # free, deterministic only
    python ingest.py ../../results --provider openrouter --model x-ai/grok-4.3
    python ingest.py ../../results --dry-run

What each ruling ends up with
-----------------------------
    from the file itself     the text, the Word document, and the PII gate's verdict
    from the pipeline        chamber, numbers, date, city, year
    from the page            subject, keyword chain, the court's own rule, outcome
    from a model (optional)  a subject and a summary, but only where the court
                             printed none, written to their own columns and labelled

The court's words are never overwritten. `rule` only ever holds what the court wrote;
anything a model writes goes to `abstract`, and `theme_source` says which is which.

Rules this keeps
----------------
  - a ruling the pipeline held back is not imported;
  - every file is re-scanned for PII before it is stored, whatever the pipeline said;
  - a ruling edited by hand on the site is left exactly as edited;
  - a subject a model invents is not adopted: it is written to a proposals file for a
    person to approve, and that ruling keeps its summary but no subject.

Safe to interrupt. Work is committed in batches and already-done rulings are skipped,
so running it again costs only what was left.
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

try:
    _backend = Path(__file__).resolve().parents[1] / "backend"
except NameError:
    _backend = Path.cwd()
if not (_backend / "db.py").exists():
    _backend = Path.cwd()
sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db            # noqa: E402
import extract       # noqa: E402
import headnotes     # noqa: E402
from filestore import LocalFileStore, get_filestore  # noqa: E402

STORE = get_filestore()


def _row(rec: dict) -> dict:
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


def _read_one(job: tuple) -> tuple:
    """In a worker: open the file and take everything it carries.

    Only the text and the fields come back, never the file itself -- the main process
    copies that from disk, which costs nothing.
    """
    doc_id, path, name = job
    got = extract.read(name, Path(path).read_bytes())
    return doc_id, got


def _store(name: str, path: Path) -> None:
    if isinstance(STORE, LocalFileStore):
        STORE.base.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, STORE.base / name)
    else:
        STORE.put(name, path.read_bytes())


def read_folder(results: Path, *, publish: bool, actor: str, workers: int,
                batch: int, dry_run: bool) -> dict:
    records = json.loads((results / "records.json").read_text(encoding="utf-8"))
    counts = {"imported": 0, "updated": 0, "held_by_pipeline": 0, "no_file": 0,
              "gate_quarantined": 0, "kept_edited": 0, "unreadable": 0,
              "with_subject": 0, "with_rule": 0, "with_outcome": 0}

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
    print(f"  reading {len(jobs):,} rulings with {workers} workers", flush=True)
    started, done, pending = time.time(), 0, []

    def flush():
        if pending and not dry_run:
            for k, v in db.upsert_many(pending, publish=publish).items():
                counts[k] = counts.get(k, 0) + v
        pending.clear()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        for doc_id, got in pool.map(_read_one, jobs, chunksize=16):
            done += 1
            rec, name, path = keep[doc_id]
            if got.error:
                counts["unreadable"] += 1
            elif not got.clean:                  # the gate, whatever the pipeline said
                counts["gate_quarantined"] += 1
            else:
                row = _row(rec)
                row.update(extract.fields(got))
                counts["with_subject"] += bool(got.theme)
                counts["with_rule"] += bool(got.rule)
                counts["with_outcome"] += bool(got.outcome)
                pending.append((row, got.text, name, rec.get("links") or []))
                if not dry_run:
                    _store(name, path)
            if len(pending) >= batch:
                flush()
            if done % 2000 == 0:
                print(f"  {done:,}/{len(jobs):,}  "
                      f"({done/max(1e-9, time.time()-started):.0f}/s)", flush=True)
    flush()
    if not dry_run:
        db.add_audit(actor, "ingest", "folder", str(results),
                     new=", ".join(f"{k}={v}" for k, v in counts.items()))
    counts["seconds"] = round(time.time() - started, 1)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest a pipeline results folder")
    ap.add_argument("results", help="the folder holding records.json")
    ap.add_argument("--no-publish", action="store_true", help="import for review instead")
    ap.add_argument("--no-model", action="store_true",
                    help="skip the model pass: nothing leaves this machine")
    ap.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "gemini"),
                    choices=["gemini", "openrouter"])
    ap.add_argument("--model", default="", help="override the provider's default model")
    ap.add_argument("--actor", default="ingest", help="who to record in the audit log")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--batch", type=int, default=400)
    ap.add_argument("--dry-run", action="store_true", help="read and count, write nothing")
    args = ap.parse_args()

    results = Path(args.results)
    if not (results / "records.json").exists():
        print(f"No records.json in {results}", file=sys.stderr)
        return 2

    db.init_db()
    print("step 1/2  reading the rulings")
    counts = read_folder(results, publish=not args.no_publish, actor=args.actor,
                         workers=args.workers, batch=args.batch, dry_run=args.dry_run)
    print(json.dumps(counts, ensure_ascii=False, indent=2))

    if args.no_model or args.dry_run:
        print("\nstep 2/2  skipped (--no-model)" if args.no_model else "\nstep 2/2  skipped (dry run)")
    else:
        print("\nstep 2/2  asking a model for the rulings that printed nothing")
        import classify_rulings
        sys.argv = ["classify_rulings", "--provider", args.provider]
        if args.model:
            sys.argv += ["--model", args.model]
        classify_rulings.main()

    print("\n" + json.dumps(db.counts(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
