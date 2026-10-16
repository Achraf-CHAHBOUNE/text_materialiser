#!/usr/bin/env bash
# Back up the platform: the database (pg_dump) and the Word files (from Garage), taken
# together into one folder, so either can be restored with the other.
#
#   ./scripts/backup.sh                 # -> backups/<date-time>/ beside platform/
#   ./scripts/backup.sh /mnt/disk/tok   # somewhere else (another disk is better)
#
# Each backup is complete on its own. Unchanged files are hard-linked to the previous
# backup, so a nightly run costs only what changed. The newest KEEP backups (default
# 14) are kept.
#
# On a server, say which compose files to use:
#   COMPOSE="docker compose -f docker-compose.yml -f docker-compose.server.yml" ./scripts/backup.sh
# Nightly at 03:30, from the platform folder:
#   (crontab -l 2>/dev/null; echo "30 3 * * * cd $PWD && ./scripts/backup.sh >> backups/backup.log 2>&1") | crontab -
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
ROOT="${1:-backups}"
KEEP="${KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$ROOT/$STAMP"
ROOT_ABS="$(cd "$ROOT" && pwd)"
DEST="$ROOT_ABS/$STAMP"
set -a; . ./.env; set +a

echo "Backing up to $DEST"
# 1. the database, in pg_dump's own format: compressed, restorable table by table
$COMPOSE exec -T postgres pg_dump -U "${POSTGRES_USER:-anon}" -d "${POSTGRES_DB:-anonymize}" -Fc \
  > "$DEST/database.dump"
echo "  database: $(du -h "$DEST/database.dump" | cut -f1)"

# 2. the files, by the backend itself (it holds the store's keys); as root inside the
#    one-off container so it may write to the mounted folder whatever its owner
$COMPOSE run --rm --no-deps -T -u 0 -v "$ROOT_ABS:/backups" backend \
  python -m ops.backup save "/backups/$STAMP"

# 3. the settings, so a restore on a new machine can start (secrets: keep it private)
cp .env "$DEST/env.txt" && chmod 600 "$DEST/env.txt"

# keep the newest $KEEP finished backups
ls -1d "$ROOT_ABS"/2*/ 2>/dev/null | sort | head -n "-$KEEP" | xargs -r rm -rf
echo "Done."
