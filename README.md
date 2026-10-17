# Moroccan Court Decisions — Anonymization & Consultation

Two **separate** products with a deliberate air-gap between them. Raw, PII-bearing
documents are handled only by the pipeline, on a secure machine. Only anonymized
output ever crosses into the platform.

```
   raw .doc / .docx / .pdf / scans
              │
              ▼
   ┌───────────────────────┐
   │  1 — pipeline         │   read · extract · classify · link · anonymize · leak-test
   │  CLI, containerized   │
   └──────────┬────────────┘
              │  records.json / .xlsx  +  the anonymized files   ← the ONLY hand-off
              ▼
   ┌───────────────────────┐
   │  2 — platform         │   ingest-gate · review/publish · browse · search · edit
   │  web app              │
   └───────────────────────┘
```

> **The original, non-anonymized documents never enter the platform.** Not in storage,
> not in a backup, not in a temporary folder.

That is why these are two codebases, two containers, and one narrow, audited hand-off.
`data/`, `results/` and `lastinput/` hold real names and are never committed.

---

## Where it stands

The full corpus has been processed and is being served.

| | |
|---|---|
| input | 51,804 PDFs, of which 22,354 were byte-identical copies |
| delivered | **29,384 rulings** · 7 chambers · 1964–2025 · 70 cities |
| cost to anonymize | **$29.17**, all leak-tests passed |
| on the platform | 29,383 published |
| subject · summary · outcome | **97.3% · 87.8% · 76.5%** |
| search within a chamber | **36–52 ms** over 29,383 rulings |

---

## 1 · The pipeline — turning raw files into safe ones

Put a client folder in `data/corpus/`, then:

```bash
run.bat 01_civile                  # Windows — everything left to do
./run.sh 01_civile --sample 200    # a random 200 first, as a test
```

It anonymizes that folder into `data/work/01_civile/`, then rebuilds `results/` from
every folder processed so far. Stopping and re-running is safe: finished rulings are
skipped and nothing is paid for twice. Byte-identical copies — within a folder or
across folders — are processed once.

`results/` holds `listing.csv`, `records.json` / `.xlsx`, and `documents/<chamber>/`.
`results/upload/01_civile.zip` holds just that folder's rulings, ready for the platform:
*Administration › Import › Choisir un .zip*.
Anything the leak check held back stays in `data/work/<folder>/_quarantine/` and never
reaches `results/`.

Details: [`pipeline/README.md`](pipeline/README.md) ·
[`pipeline/docs/TECHNICAL_DESIGN.md`](pipeline/docs/TECHNICAL_DESIGN.md)

---

## 2 · The platform — making them searchable

### Run it locally

```bash
cd platform
./run-local.sh            # starts the API and the site, prints the address and login
./run-local.sh stop
```

### Load a delivery into it

One command. A ruling is opened once and everything it carries is read at once:

```bash
cd platform/scripts
python ingest.py ../../results
python ingest.py ../../results --no-model     # free; nothing leaves the machine
```

| what it reads | from | coverage |
|---|---|---|
| text, Word file | the file, after the PII gate re-checks it | 100% |
| chamber, numbers, date, city | the pipeline's `records.json` | 93–100% |
| **الموضوع** subject · **المفاتيح** keywords | the headnote the court printed | 42.5% |
| **القاعدة** the court's own rule | the sentence after it | 31.3% |
| **المنطوق** outcome | the heading, or the closing after `لهذه الأسباب` | 76.5% |
| **ملخص** summary | a model, **only** where the court printed none | 56.5% |

More than half the corpus — most of the civil chamber — prints no headnote at all, so
a model is asked for those. **What it writes is kept apart and labelled**: `rule` only
ever holds the court's sentence, a model's goes to `abstract`, and the page says which
in words — «من نص القرار» against «تحرير آلي» — not only in colour.

A subject the model invents is **never** adopted. It waits for a person:

```bash
python approve_subjects.py review    # a short list, commonest first
python approve_subjects.py apply
```

Full guide: [`platform/scripts/README.md`](platform/scripts/README.md)

### Deploy it

```bash
# on the server, from /opt/tok/platform
TRANSLATE_API_KEY=... ./deploy-vps.sh <hostname>
```

Builds the two images, starts Postgres, backend, frontend and Caddy under the compose
project `tok`, and gets a TLS certificate. It never prunes, never removes an image it
did not build, never restarts the Docker daemon — it is written to share a machine
that is busy with someone else's work.

Details: [`platform/README.md`](platform/README.md)

---

## Configuration

Secrets go in `platform/.env` and `pipeline/.env`, both gitignored. Copy the
`.env.example` beside each to start.

```bash
# platform/.env
DATABASE_URL=postgresql+psycopg://…   # or DB_DIR=… for SQLite in development
FILESTORE_DIR=…
GEMINI_API_KEY=…                      # only for the model step of ingest
OPENROUTER_API_KEY=…                  # only if --provider openrouter
```

In Docker the environment comes from compose instead and always wins.

---

## What the platform does

- **browse** court → chamber → year → city, the way a court portal is read
- **search** the full text in Arabic, tolerant of أ/ا, ي/ى, ة/ه, diacritics and digits
- **filter** by subject, year and city, each a menu you can type into
- **read** a ruling beside a French translation, generated on demand and cached
- **edit** a ruling by hand — the Word file is edited too, with full version history;
  removals publish straight away, additions wait for an admin
- **export** every correction, and a full audit trail
- **in two languages**: every page at `/ar/…` and `/fr/…`, the rulings, abstracts,
  subjects and search in French, the Arabic always one click away
- **sell and serve**: organizations with seats and subscriptions, a CRM (leads,
  pipeline, renewals, customers at risk), numbered invoices and payments, support
  tickets, a reader's folders, alerts and history, counted and marked downloads, and a
  worker for emails and reminders -- see [`platform/docs/BUSINESS.md`](platform/docs/BUSINESS.md)

---

## Tests

```bash
cd platform/backend && python -m pytest tests/ -q
cd pipeline && python -m pytest -q
```

Both run in CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). The platform's
suite covers the import gate, the publication workflow, hand editing, translation, the
headnote parser, the outcome parser and the search query builder. Rules that matter are
mutation-checked: the rule is deliberately broken to confirm a test fails.

---

## Layout

| path | what it is |
|---|---|
| [`pipeline/`](pipeline/) | the CLI that anonymizes. Touches raw PII; never networked to the platform. |
| [`platform/backend/`](platform/backend/) | FastAPI · SQLAlchemy · Postgres (SQLite in development) |
| [`platform/frontend/`](platform/frontend/) | React · TanStack Router · Tailwind, right-to-left |
| [`platform/scripts/`](platform/scripts/) | ingest, backfill, subject approval, backup, migrations |
| `data/` · `results/` · `lastinput/` | **real data — never committed** |
