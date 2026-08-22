# Project 2 — Web platform

Web platform for consulting **anonymized** Moroccan court decisions. Three parts:
admin integration (import/review/publish), admin clients (accounts), and the client
space (browse/search/view).

Brief: [`../website_brief.md`](../website_brief.md).

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
