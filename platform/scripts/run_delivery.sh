#!/usr/bin/env bash
# Unattended delivery run: a small pilot first, and the full run only if the pilot is
# healthy. Everything goes to ../../delivery; the log is delivery/run.log.
set -u
cd "$(dirname "$0")"
export DB_DIR="$(cd ../.. && pwd)/data/platform"
export FILESTORE_DIR="$DB_DIR/files"
OUT=../../delivery
mkdir -p "$OUT"
LOG="$OUT/run.log"

echo "=== pilot: 40 rulings across the chambers   $(date)" | tee -a "$LOG"
python deliver.py --out "$OUT" --limit 40 --sample --workers 40 >> "$LOG" 2>&1

# The gate: stop rather than spend $28 producing broken files.
python - "$OUT/report.csv" <<'PY' >> "$LOG" 2>&1
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
fr = sum(1 for r in rows if r["french"] == "yes")
ar = sum(1 for r in rows if r["arabic"] == "yes")
print(f"pilot: {ar}/{len(rows)} Arabic, {fr}/{len(rows)} French")
if not rows or ar < len(rows) * 0.95 or fr < len(rows) * 0.80:
    print("PILOT FAILED -- full run not started")
    sys.exit(1)
print("pilot healthy -- starting the full run")
PY
if [ $? -ne 0 ]; then echo "=== STOPPED after the pilot   $(date)" | tee -a "$LOG"; exit 1; fi

echo "=== full run   $(date)" | tee -a "$LOG"
python deliver.py --out "$OUT" --workers 96 >> "$LOG" 2>&1
echo "=== finished   $(date)" | tee -a "$LOG"
