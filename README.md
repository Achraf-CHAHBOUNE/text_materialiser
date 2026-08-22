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
| [`pipeline/`](pipeline/)   | 1 | [`Script.md`](Script.md)         | Batch **CLI** that turns raw files into anonymized files + JSON/XLSX metadata. No web server. |
| [`platform/`](platform/)   | 2 | [`website_brief.md`](website_brief.md) | **Web platform**: admin integration, client accounts, client space. Ingests only Project 1 output. |

## The hard rule

> **The original, non-anonymized documents never enter the platform.** Not in storage,
> not in a backup, not in a temporary folder. (`website_brief.md` §4)

That is why these are two codebases, two containers, and one narrow, audited hand-off.

## Status

- **Project 1** — pipeline built & tested (20 tests): read/extract/classify/link/
  anonymize, **leak-test release gate**, JSON/XLSX output, budget ceiling, idempotence,
  evaluation harness, container + CI. Pending: full-corpus audit + live container smoke-test.
  See [`pipeline/README.md`](pipeline/README.md) and [`pipeline/docs/TECHNICAL_DESIGN.md`](pipeline/docs/TECHNICAL_DESIGN.md).
- **Project 2** — reworked to the ingest-only import-gate architecture & tested (9 tests):
  import gate, publication workflow, audit trail, client CRUD, Arabic search, admin console
  frontend. See [`platform/README.md`](platform/README.md).

Both projects run in CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
