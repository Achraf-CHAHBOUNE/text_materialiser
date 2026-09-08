#!/usr/bin/env bash
# Anonymize the NEXT 500 documents. Safe to re-run; finished files are skipped.
cd "$(dirname "$0")/pipeline" || exit 1
export PYTHONUTF8=1
export STATE_FILE="../output_first/.state.json"
export DB_PATH="../output_first/cases.db"
python -m anonymizer --input "../02_statut_personnel" --output "../output_first" \
  --workers 32 --budget 10 --limit 500
echo
echo "Chunk finished. Run again for the next 500. '0 to process' = complete."
