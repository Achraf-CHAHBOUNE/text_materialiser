#!/usr/bin/env bash
# Put the platform back as it was at one backup made by backup.sh: the database and
# the Word files together.
#
#   ./scripts/restore.sh backups/20261016-033000
#
# Destructive: what the platform holds now is replaced by the backup. The site is
# stopped meanwhile and started again at the end. Postgres and Garage keep running.
# On a server, set COMPOSE as for backup.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
SRC="$(cd "${1:?usage: restore.sh BACKUP_FOLDER}" && pwd)"
[ -f "$SRC/database.dump" ] && [ -f "$SRC/files/manifest.json" ] \
  || { echo "Not a finished backup: $SRC (database.dump or files/manifest.json missing)"; exit 1; }
set -a; . ./.env; set +a

if [ "${YES:-}" != "1" ]; then
  read -r -p "Replace everything the platform holds with the backup $(basename "$SRC")? [yes/no] " ok
  [ "$ok" = "yes" ] || { echo "Nothing changed."; exit 1; }
fi

echo "Stopping the site ..."
$COMPOSE stop proxy frontend worker backend

echo "Restoring the database ..."
$COMPOSE exec -T postgres pg_restore -U "${POSTGRES_USER:-anon}" -d "${POSTGRES_DB:-anonymize}" \
  --clean --if-exists --no-owner < "$SRC/database.dump"

echo "Restoring the files ..."
$COMPOSE run --rm --no-deps -T -u 0 -v "$SRC:/restore:ro" backend \
  python -m ops.backup restore /restore

echo "Starting the site ..."
$COMPOSE up -d
echo "Restored from $(basename "$SRC")."
