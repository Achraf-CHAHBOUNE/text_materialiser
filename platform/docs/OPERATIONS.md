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

What cannot be rebuilt lives in two places: Postgres (rulings, accounts, contracts,
every correction and the audit trail) and Garage (the Word files as they stand now --
a corrected ruling's file differs from what the pipeline produced). A backup takes both
together into one folder:

```bash
./scripts/backup.sh                        # -> backups/<date-time>/
./scripts/backup.sh /mnt/other-disk/tok    # better: another disk, or another machine
./scripts/restore.sh backups/<date-time>   # destructive: asks first (YES=1 skips)
```

Each folder holds `database.dump` (pg_dump), `files/` with a `manifest.json`, and
`env.txt` (a copy of `.env`: secrets, keep it private). Each backup is complete on its
own; files unchanged since the previous one are hard-linked, so nightly backups cost
what changed. The newest 14 are kept (`KEEP=30` for more).

On a server, run it nightly (the line is in the script's header) and copy the folder
off the machine. Try a restore now and then -- a backup never restored is a hope.

## 5. Changing the database's structure

Every change is a numbered migration in `backend/migrations/versions/`, applied by the
backend at start (one copy migrates, the others wait):

```bash
cd backend
alembic revision --autogenerate -m "what changes"   # write it -- then read it
alembic upgrade head                                # apply by hand, if wanted
alembic downgrade -1                                # undo the last one
```

Run `alembic check` against Postgres: on SQLite a few NOT NULL differences are expected
(see migration 0002).

## 6. Logs

Every service writes one JSON line per event to stdout: `docker compose logs -f backend`.
Each request carries an id, returned to the browser as `X-Request-ID`; a reader who
reports a problem can quote it. Requests are logged by route pattern, never by address
or query, so no search and no email reaches the logs. `LOG_FORMAT=text` for plain lines.

## 7. Scale notes

- **More readers:** `docker compose ... up -d --scale backend=3` (or `API_WORKERS` per
  container). No backend copy keeps anything of its own: sessions, limits and locks are
  in Postgres, files in Garage, and Caddy spreads the requests.
- **More workers:** they can be scaled too; a lock in Postgres lets one at a time run
  the daily jobs, the mail, the imports and the model step.
- **Search:** Arabic is normalized into `search_text`, matched by a `pg_trgm` index and a
  stored word index (`search_tsv`); French by a stored French `tsvector`.
- **Files:** Garage runs one node with one copy. For several machines, raise
  `replication_factor` in `deploy/garage.toml` and add nodes; nothing in the code changes.
