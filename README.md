# Moroccan Court Decisions — Anonymization & Consultation

Two **separate** products with a deliberate air-gap between them. Raw, PII-bearing
documents are handled only by Project 1, on a secure machine. Only anonymized output
ever crosses into Project 2.

```
   raw .doc/.docx/.pdf/images
              │
              ▼
   ┌───────────────────────┐
   │  Project 1 — pipeline │   read · extract · classify · link · anonymize · leak-test
   │  (CLI, containerized) │
   └──────────┬────────────┘
              │  JSON / XLSX records  +  anonymized "safe" files   ← the ONLY hand-off
              ▼
   ┌───────────────────────┐
   │  Project 2 — platform │   import-gate · admin review/publish · client browse/search/view
   │  (web app)            │
   └───────────────────────┘
```

## Folders

| Folder                | Project | Brief              | What it is |
| --------------------- | ------- | ------------------ | ---------- |
| [`pipeline/`](pipeline/)   | 1 | [`docs/Script.md`](docs/Script.md)         | Batch **CLI** that turns raw files into anonymized files + JSON/XLSX metadata. No web server. |
| [`platform/`](platform/)   | 2 | [`docs/website_brief.md`](docs/website_brief.md) | **Web platform**: admin integration, client accounts, client space. Ingests only Project 1 output. |
| `data/`                    | — | —                  | **All real data, never committed.** `corpus/` the client's raw folders (+ `archives/`), `work/` the pipeline's working state per folder and the shared `cases.db`, `old/` superseded hand-offs and backups. |
| `results/`                 | — | —                  | **The one hand-off for the client**: every delivered ruling from every folder, rebuilt on each run. Never committed. |

## Running

Put a client folder in `data/corpus/`, then:

```
run.bat 01_civile                 # Windows — everything left to do
./run.sh 01_civile --sample 200   # a random 200 first, as a test
```

It anonymizes that folder into `data/work/01_civile/`, then rebuilds `results/` from
every folder processed so far. Stopping and rerunning is safe: finished rulings are
skipped and nothing is paid for twice. Byte-identical copies of a ruling — within a
folder or across folders — are processed once.

`results/` holds `listing.csv` (court, chamber, year, number, date, city — one row per
ruling), `records.json` / `records.xlsx`, and `documents/<chamber>/`. Files the leak
check held back stay in `data/work/<folder>/_quarantine/` and never reach `results/`.

## The hard rule

> **The original, non-anonymized documents never enter the platform.** Not in storage,
> not in a backup, not in a temporary folder. (`docs/website_brief.md` §4)

That is why these are two codebases, two containers, and one narrow, audited hand-off.

## Status

- **Project 1** — pipeline built & tested (150 tests): read/extract/classify/link/
  anonymize, **leak-test release gate**, JSON/XLSX output, budget ceiling, idempotence,
  evaluation harness, container + CI. Pending: full-corpus audit + live container smoke-test.
  See [`pipeline/README.md`](pipeline/README.md) and [`pipeline/docs/TECHNICAL_DESIGN.md`](pipeline/docs/TECHNICAL_DESIGN.md).
- **Project 2** — reworked to the ingest-only import-gate architecture & tested (10 tests):
  import gate, publication workflow, audit trail, client CRUD, Arabic search, admin console
  frontend. See [`platform/README.md`](platform/README.md).

Both projects run in CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
