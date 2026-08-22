#!/usr/bin/env bash
# Restore the platform's state from a backup made by backup.sh.
#
#   ./scripts/restore.sh BACKUP_DIR
#
# Stops the stack, replaces the volume contents, and restarts. Destructive — the
# current data is overwritten by the backup.
set -euo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-platform}"
SRC="${1:?usage: restore.sh BACKUP_DIR}"
ABS="$(cd "$SRC" && pwd)"
[ -f "$ABS/pg-data.tgz" ] && [ -f "$ABS/minio-data.tgz" ] || { echo "backup files missing in $ABS"; exit 1; }

echo "Stopping stack ..."
docker compose down

for vol in pg-data minio-data; do
  echo "Restoring ${PROJECT}_${vol} ..."
  docker volume create "${PROJECT}_${vol}" >/dev/null
  docker run --rm -v "${PROJECT}_${vol}:/data" -v "$ABS:/b" alpine \
    sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null; tar xzf /b/${vol}.tgz -C /data"
done

echo "Starting stack ..."
docker compose up -d
echo "Restore complete."
