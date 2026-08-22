#!/usr/bin/env bash
# Back up the platform's state: Postgres (metadata + audit) and MinIO (anonymized files).
# Volume-level snapshot — no extra tooling, works whatever the row count.
#
#   ./scripts/backup.sh [DEST_DIR]     # default: backups/<timestamp>
#
# Run from the platform/ folder with the stack (or at least its volumes) present.
set -euo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-platform}"
TS="$(date +%Y%m%d-%H%M%S)"
DEST="${1:-backups/$TS}"
mkdir -p "$DEST"
ABS="$(cd "$DEST" && pwd)"

echo "Backing up to $ABS ..."
docker run --rm -v "${PROJECT}_pg-data:/data:ro"    -v "$ABS:/b" alpine \
  tar czf /b/pg-data.tgz    -C /data .
docker run --rm -v "${PROJECT}_minio-data:/data:ro" -v "$ABS:/b" alpine \
  tar czf /b/minio-data.tgz -C /data .

echo "Done: $ABS/{pg-data.tgz,minio-data.tgz}"
