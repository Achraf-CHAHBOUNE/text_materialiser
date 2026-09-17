# Project 2 — Web platform

Web platform for consulting **anonymized** Moroccan court decisions. Three parts:
admin integration (import/review/publish), admin clients (accounts), and the client
space (browse/search/view).

Brief: [`../docs/website_brief.md`](../docs/website_brief.md).

## The boundary

> The original, non-anonymized documents never enter this platform.

The platform ingests **only** Project 1 output — JSON/XLSX records plus anonymized
files — through an **import gate** that re-checks for PII and rejects anything unclean.

## Layout

```
backend/     FastAPI service (auth, DB, object storage)
frontend/    React + TanStack app (admin + client UI)
docs/        design notes and prompts
docker-compose.yml   backend + frontend + MinIO + Postgres
```

## Browse (the client space)

Rulings are read the way a court portal is read — **court → chamber → year → ruling** —
following the layout the client asked for:

| Page | What it shows |
| --- | --- |
| `/browse` | every court with its chambers, each in its own colour, with counts |
| `/browse/$chamber` | the listing: رقم القرار · تاريخ القرار · المدينة · الغرفة, with year chips, a city filter, search and paging |
| `/ruling/$docId` | the ruling's text and fields, with download and print |

**المدينة** is the city of the lower court the appeal came from: the Court of
Cassation sits only in Rabat, so its own city would say nothing.

## Load a pipeline results folder

```bash
cd backend
python import_results.py ../../results          # import and publish
python import_results.py ../../results --no-publish   # import for review instead
```

Reads the folder directly (no browser upload), applying the same rules as the HTTP
import: files the pipeline held back are refused, every file is re-scanned by the PII
gate, and re-importing a ruling updates it rather than duplicating it.

## Correcting a ruling

Admins correct a ruling on its own page; the Word file is changed with it.

- **Hide**: select a name in the text, then *Hide* (this occurrence) or *Hide
  everywhere* (every whole-word match, previewed with a count and context first).
  Live immediately.
- **Edit text**: edit the whole text, review the change (removed in red, added in
  green), save.
- **Edit details**: number, date, city, file number, chamber. A new chamber also
  retitles the Word file.

What happens on save is decided by what the change does, not by who makes it:

| the change | result |
| --- | --- |
| only removes text (hiding, deleting) | live at once |
| adds any text (a corrected word, a restored name) | a **draft**, published only when an admin approves it |
| contains an e-mail, phone, ID or IBAN pattern | refused |

The text a reader sees *is* the Word file: an edit rewrites only the paragraphs whose
line changed (title, headings and page breaks untouched), and the text is read back
from the saved file. Every applied change is a version; **Restore** goes back to one
(as a draft if it would show hidden text again). **Delete older versions** removes the
last copy of a name once a hide is certain. An edit made on a version someone has
since replaced is refused, never merged silently.

Readers cannot edit: they select text and **Report a problem**. Reports and drafts
from every ruling are listed under **Corrections**; the quoted text of a report is
erased once it is handled.

**Re-imports never undo a correction.** A hand-edited ruling is skipped by both
imports and listed as `kept_edited`.

**Getting corrections into the client's folder.** `results/` is built by the
pipeline, so corrections made here reach it through an export: *Corrections →
Export edited rulings* downloads `edits.zip`, then

```bash
cd pipeline
python -m anonymizer.assemble --work ../data/work --out ../results --edits edits.zip
```

The edits are re-applied on every rebuild, and never written into the pipeline's
own working folders.

## Where the files live

The anonymized `.docx` files sit either in a folder or in object storage. The backend
speaks one protocol (S3) to AWS S3, Google Cloud Storage and MinIO alike, so moving
between them is a change of settings, never of code.

| | set | used for |
| --- | --- | --- |
| a folder | nothing (default `FILESTORE_DIR=data/files`) | development, and a single server |
| MinIO | `S3_ENDPOINT=minio:9000`, `S3_SECURE=false`, `S3_CREATE_BUCKET=true` | the docker-compose stack |
| AWS S3 | `S3_ENDPOINT=s3.amazonaws.com`, `S3_REGION`, keys | more than one server |
| Google Cloud Storage | `S3_ENDPOINT=storage.googleapis.com`, `S3_REGION`, **HMAC** keys | same, on Google |

`S3_BUCKET` names the bucket (default `anonymized`). For GCS the keys are HMAC keys,
made in Cloud Storage's settings for a service account — not a JSON key file.

Create the bucket yourself once: on S3 and GCS the application's key normally may not
create buckets, and a bucket created by accident is rulings written somewhere nobody
is watching. If the bucket is missing, or the storage cannot be reached, the backend
says so at startup instead of failing on the first download. `S3_VERIFY_BUCKET=false`
skips that check for a key that may read and write objects but not look buckets up.

The storage keys have no default: anyone holding them can read every ruling, so
docker-compose refuses to start until they are set in `platform/.env`. The older
`MINIO_*` names still work everywhere.

## Run (local, without docker)

```bash
cd backend && DB_DIR=data FILESTORE_DIR=data/files AUTH_SECRET=dev-secret   SEED_EMAIL=admin@x.com SEED_PASSWORD=admin-pass   SEED_CLIENT_EMAIL=client@x.com SEED_CLIENT_PASSWORD=client-pass   python -m uvicorn server:app --port 8000
cd frontend && npm run dev        # http://localhost:8080
```

The frontend calls the API at `127.0.0.1`, not `localhost`: on Windows `localhost`
resolves to IPv6 first, the API listens on IPv4, and every request pays ~230 ms
waiting for that attempt to fail.

```bash
```

## Run (local, docker)

```bash
cp .env.example .env
docker compose up --build
# frontend  http://localhost:8080
# backend   http://localhost:8000
```

## Status

Reworked to the import-gate architecture — **no engine, no raw documents, ingest-only.**

Backend (`backend/`, ingest-only FastAPI):
- **Import gate** (`piigate.py`) — a batch `.zip` (records.json + anonymized files) is
  accepted only if each record has a matching file and that file trips no PII pattern
  (email / Moroccan phone / national-ID / IBAN). Re-import updates, never duplicates.
- **Publication workflow** `imported → under_review → published → withdrawn`; only
  published is visible to clients; withdrawal is immediate.
- **Audit trail** on every correction / state change (who, when, old, new).
- **Client accounts** — CRUD + immediate suspension (checked per request, not per login).
- **Client space** — browse/filter published decisions, one-click linked-decision
  navigation, and **Arabic-correct full-text search** (alef/ya/taa, diacritics, tatweel,
  Arabic-Indic digits all normalized) with highlighted match snippets.
- **Least privilege** — clients can't reach admin routes; no client can obtain an
  unpublished document by any route.

Frontend (`frontend/`, TanStack + React): login (role-aware), client Decisions
browse/search, decision detail with linked-decision navigation and anonymized preview,
and an **admin console** (import · review queue/publish · client management).

Tested (`backend/tests/`, in CI): permissions, the anonymized-only boundary, the import
gate, publication visibility, Arabic search, immediate suspension, audit trail.

### Remaining / scale notes
Search uses a normalized `LIKE` column (fine to ~10× the corpus); swap for Postgres FTS /
`pg_trgm` at larger scale. Backup/restore procedure and a live MinIO+Postgres compose
smoke-test are the next infra tasks.
