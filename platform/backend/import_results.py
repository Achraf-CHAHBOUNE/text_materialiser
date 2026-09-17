"""Load a pipeline `results/` folder into the platform, locally.

The HTTP import takes a .zip, which means uploading hundreds of megabytes through
the browser; for a full corpus that is slow and pointless when the folder is on the
same machine. This reads the folder directly and applies exactly the same rules as
the HTTP import:

  - a record the pipeline held back is never imported;
  - every file is re-scanned by the PII gate before it is stored;
  - re-importing the same ruling updates it instead of duplicating it.

    python import_results.py ../../results            # import and publish
    python import_results.py ../../results --no-publish
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import db
import piigate
from filestore import get_filestore
from server import _extract_text

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


def import_folder(results: Path, publish: bool, actor: str) -> dict:
    records = json.loads((results / "records.json").read_text(encoding="utf-8"))
    counts = {"imported": 0, "updated": 0, "held_by_pipeline": 0, "no_file": 0,
              "gate_quarantined": 0}
    started = time.time()
    for i, rec in enumerate(records, 1):
        if rec.get("quarantined") or rec.get("status") != "done":
            counts["held_by_pipeline"] += 1
            continue
        name = rec.get("anonymized_file") or f"{rec['doc_id']}.docx"
        path = results / (rec.get("file_path") or name)
        if not path.exists():
            counts["no_file"] += 1
            continue
        data = path.read_bytes()
        text = _extract_text(name, data)
        if piigate.scan(text):          # same gate as the HTTP import
            counts["gate_quarantined"] += 1
            continue
        existed = db.get_decision(rec["doc_id"]) is not None
        db.upsert_decision(_row(rec), body_text=text, file_name=name)
        db.set_links(rec["doc_id"], rec.get("links", []))
        STORE.put(name, data)
        if publish:
            db.set_decision_state(rec["doc_id"], "published", actor)
        counts["updated" if existed else "imported"] += 1
        if i % 500 == 0:
            rate = i / max(1e-9, time.time() - started)
            print(f"  {i:,}/{len(records):,}  ({rate:.0f}/s)", flush=True)
    db.add_audit(actor, "import", "folder", str(results),
                 new=", ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Import a pipeline results folder")
    ap.add_argument("results", help="the results folder (with records.json)")
    ap.add_argument("--no-publish", action="store_true", help="import for review instead")
    ap.add_argument("--actor", default="import-script", help="who to record in the audit log")
    args = ap.parse_args()

    results = Path(args.results)
    if not (results / "records.json").exists():
        print(f"No records.json in {results}", file=sys.stderr)
        return 2
    db.init_db()
    counts = import_folder(results, publish=not args.no_publish, actor=args.actor)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(json.dumps(db.counts(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
