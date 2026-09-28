#!/usr/bin/env bash
# Back up the platform running from docker-compose.server.yml.
#
# Two things matter and neither can be rebuilt from the pipeline: the database
# (rulings, accounts, corrections, the audit trail) and the documents as they stand
# now, which for a corrected ruling differ from what the pipeline produced.
#
#   ./scripts/server-backup.sh            # -> /var/backups/tok/<date>/
#   ./scripts/server-backup.sh /mnt/disk  # somewhere else
#
# Nightly, from the platform folder:
#   (crontab -l 2>/dev/null; echo "30 3 * * * cd $PWD && ./scripts/server-backup.sh >> /var/log/tok-backup.log 2>&1") | crontab -
set -euo pipefail

COMPOSE="docker compose -f docker-compose.server.yml"
DEST="${1:-/var/backups/tok}/$(date +%Y%m%d-%H%M)"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$DEST"

echo "Backing up to $DEST ..."
# The database, as a plain SQL dump: restorable into any PostgreSQL, not just this one.
$COMPOSE exec -T postgres pg_dump -U "${POSTGRES_USER:-anon}" "${POSTGRES_DB:-anonymize}" \
  | gzip > "$DEST/database.sql.gz"
# The documents, straight out of the volume.
docker run --rm -v platform_documents:/documents:ro -v "$DEST":/backup alpine \
  tar czf /backup/documents.tgz -C /documents .
cp .env "$DEST/env.txt"                      # the secrets, so a restore can start
chmod 600 "$DEST/env.txt"

find "${1:-/var/backups/tok}" -maxdepth 1 -type d -mtime "+$KEEP_DAYS" -exec rm -rf {} + 2>/dev/null || true
du -sh "$DEST"/* | sed 's/^/  /'
echo "Done. To restore: see docs/HOSTING-DEMO.md"
