#!/usr/bin/env bash
# The full run, then one more pass over whatever failed. Already-finished rulings are
# skipped both times, so the second pass only touches the failures. If the first pass
# is interrupted rather than finished, stop: a second pass is only for retrying.
set -u
cd "$(dirname "$0")"
export DB_DIR="$(cd ../.. && pwd)/data/platform"
export FILESTORE_DIR="$DB_DIR/files"
OUT=../../delivery
LOG="$OUT/run.log"
echo "=== run, numbered redactions + separate abstract   $(date)" | tee -a "$LOG"
python deliver.py --out "$OUT" --workers 96 >> "$LOG" 2>&1 || { echo "=== interrupted   $(date)" | tee -a "$LOG"; exit 1; }
echo "=== second pass over the failures   $(date)" | tee -a "$LOG"
python deliver.py --out "$OUT" --workers 48 >> "$LOG" 2>&1
echo "=== finished   $(date)" | tee -a "$LOG"
