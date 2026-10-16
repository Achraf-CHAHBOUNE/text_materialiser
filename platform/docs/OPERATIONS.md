# Platform — operations guide

Covers deployment, the daily import/review workflow, client accounts, and backup/restore.
Audience: whoever runs the platform day to day.

## The one rule

**No original, non-anonymized document ever enters this platform.** Only the pipeline's
output — anonymized files + `records.json` — is imported, and the import gate re-checks
every file for personal-data patterns before it is stored.

## 1. Deploy

```bash
cd platform
cp .env.example .env          # fill in every line marked REQUIRED for Docker
docker compose up --build -d  # the site: http://localhost:8080
```

Seven services start, in order: `postgres` and `garage` (the data), `storage-init`
(gives Garage its node, key and bucket, then exits), `backend` and `worker`, `frontend`,
and `proxy` (Caddy, the only one reachable from outside). `docker compose ps` shows
each one's health.

On first boot the backend seeds the admin from `SEED_EMAIL`/`SEED_PASSWORD`. Every
secret in `.env` (`AUTH_SECRET`, `POSTGRES_PASSWORD`, `GARAGE_*`, `S3_*`) is required
and has no default; the stack refuses to start without them.

On a server: `docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build`
with `SITE_ADDRESS` set to the hostname.

### Moving in

A platform that ran on SQLite and a folder (`run-local.sh`, `data/platform/`) moves into
the stack with one command, run once the stack is up. The source is only read; a move
that stops half-way is simply run again.

```bash
docker compose run --rm -v "$PWD/../data/platform:/source:ro" backend     python -m ops.migrate --sqlite /source/app.db --files /source/files --replace
```

`--replace` empties the new database first (the backend has already seeded it with
the plans and the admin). It ends by checking the row count of every table and the
name and size of every file, and comparing 200 files byte for byte; it fails loudly if
anything differs.

## 2. Daily workflow (admin)

1. **Produce output offline.** Run the Project 1 pipeline on the secure machine; it emits
   `records.json` + anonymized files under its `output/`.
2. **Import.** Admin console → *Import* → choose the batch `.zip` (records.json + files).
   The **import gate** reports: imported, updated, rejected (no matching file), and
   **quarantined** (still contains PII patterns — email/phone/national-ID/IBAN). Quarantined
   items are *not* stored; fix them in the pipeline and re-import (re-import updates, never
   duplicates).
3. **Review.** *Review queue* lists what needs attention (missing category/identifier,
   low-confidence link). Correct fields inline (every change is audited: who/when/old/new).
4. **Publish.** Publish from the queue. Only **published** decisions are visible to clients;
   withdrawing takes effect immediately.

## 3. Client accounts (admin)

Admin console → *Clients*: create, suspend/activate (immediate — checked on every request,
not at next login), or delete. Clients can only browse/search/view **published** decisions;
they can never reach an admin route or obtain an unpublished/unclean file by any route.

## 4. Backup & restore

State lives in two Docker volumes: `*_pg-data` (Postgres: metadata, audit, accounts) and
`*_minio-data` (anonymized files). Snapshot both together:

```bash
./scripts/backup.sh                 # -> backups/<timestamp>/{pg-data.tgz,minio-data.tgz}
./scripts/restore.sh backups/<ts>   # stops stack, replaces volumes, restarts (destructive)
```

Schedule `backup.sh` (cron/Task Scheduler) and keep copies off-host. Test a restore into a
throwaway project (`COMPOSE_PROJECT_NAME=platform_test`) periodically.

For a logical, portable DB dump instead of the volume snapshot:

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > db.sql
docker compose exec -T postgres psql   -U "$POSTGRES_USER" "$POSTGRES_DB" < db.sql   # restore
```

## 5. Scale notes

Search normalizes Arabic (alef/ya/taa, diacritics, tatweel, Arabic-Indic digits) into a
`search_text` column. On Postgres a `pg_trgm` GIN index is created automatically so
`LIKE '%q%'` stays fast well beyond the initial corpus. If you outgrow that, move to a
`tsvector`/`websearch_to_tsquery` column with a custom Arabic normalization dictionary.
