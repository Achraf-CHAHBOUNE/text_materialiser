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
cp .env.example .env          # set AUTH_SECRET, SEED_EMAIL, SEED_PASSWORD, DB/MinIO creds
docker compose up --build -d
# frontend  http://localhost:8080
# backend   http://localhost:8000/health
# MinIO console http://localhost:9001
```

On first boot the backend seeds the admin from `SEED_EMAIL`/`SEED_PASSWORD` (and an
optional demo client from `SEED_CLIENT_EMAIL`/`SEED_CLIENT_PASSWORD`). Change
`AUTH_SECRET` before production — it signs every session token.

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
