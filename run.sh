#!/usr/bin/env bash
# Anonymize one client folder, then rebuild results/ for the client.
#   ./run.sh 01_civile                everything left to do
#   ./run.sh 01_civile --limit 500    only the next 500
#   ./run.sh 01_civile --sample 200   a random 200, as a test
# The folder must sit in data/corpus/. Safe to stop and run again: finished
# rulings are skipped and nothing is paid for twice.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [ $# -lt 1 ]; then
  echo "Usage: ./run.sh FOLDER [options]    -- folders in data/corpus:"; ls "$here/data/corpus"; exit 1
fi
name="$1"; shift
cd "$here/pipeline"
export PYTHONUTF8=1 STATE_FILE="../data/work/$name/.state.json" DB_PATH="../data/work/cases.db"
python -m anonymizer --input "../data/corpus/$name" --output "../data/work/$name" \
  --corpus "$name" --workers 16 --budget 15 "$@"
python -m anonymizer.assemble --work ../data/work --out ../results
echo "Done. The client hand-off is in results/."
