# Ingesting a delivery of rulings

One command turns a folder of anonymized rulings into a searchable corpus:

```bash
cd platform/scripts
python ingest.py ../../results
```

It used to take four passes that each re-read the same 29,000 files. Now a ruling is
opened once and everything that can be learned from it is learned at once.

---

## What a ruling ends up with

| field | where it comes from | coverage |
|---|---|---|
| text, Word file | the file itself, after the PII gate re-checks it | 100% |
| chamber, numbers, date, city, year | the pipeline's `records.json` | 93–100% |
| **الموضوع** · subject | the headnote the court printed | 42.5% |
| **المفاتيح** · keyword chain | the same line | 42.5% |
| **القاعدة** · the court's own rule | the sentence after it | 31.3% |
| **المنطوق** · outcome | the heading, or the closing after `لهذه الأسباب` | 76.5% |
| **ملخص** · summary | a model, **only** where the court printed none | 56.5% |

After both steps, **97% of rulings have a subject and 88% have a summary**, against
42.5% and 31.3% from the page alone.

### The court's words are never overwritten

`rule` only ever holds what the court wrote. Anything a model writes goes to a separate
`abstract` column, and `theme_source` records which is which (`court` or `model`). The
site shows the difference in words, not only colour — «من نص القرار» against «تحرير
آلي» — so a reader always knows whose sentence they are reading.

---

## How it works

```
  results/                      a delivery from the anonymizing pipeline
    records.json                what the pipeline knows about each ruling
    *.docx                      the anonymized documents
        │
        ▼
  STEP 1 — read, in worker processes, one pass per ruling      free, offline
        │
        │   extract.read(file)
        │     ├ text            textextract
        │     ├ PII gate        piigate — re-checked here, whatever the pipeline said
        │     ├ headnote        headnotes.read → subject · chain · the court's rule
        │     └ outcome         heading near the top, or the closing at the end
        │
        ├── held back by the pipeline ──► skipped
        ├── fails the PII gate ────────► quarantined, never stored
        ├── edited by hand on the site ► left exactly as edited
        └── otherwise ─────────────────► row + Word file written, in batches of 400
        │
        ▼
  STEP 2 — ask a model, only for rulings that printed no headnote     ~$0.0003 each
        │
        │   each request carries that chamber's existing subjects
        │        │
        │        ▼
        │   { theme, abstract }
        │        │
        │   is the theme one of ours?  ← checked in our code, never taken on trust
        │        ├ yes → written, theme_source = "model"
        │        └ no  → parked in proposed_subjects.json for a person to approve;
        │                the ruling keeps its summary but gets no subject
        ▼
  searchable
```

Both steps are safe to interrupt. Work commits in batches and finished rulings are
skipped, so running it again costs only what was left.

---

## Every option

### `ingest.py <results-folder>` — the one you want

| flag | default | what it does |
|---|---|---|
| `--no-model` | off | skip step 2. Free, and nothing leaves the machine. |
| `--no-publish` | off | import for review instead of publishing straight away |
| `--provider` | `gemini` | `gemini` · `openrouter` · `opencode` |
| `--model` | the provider's | override the model id |
| `--workers` | cores, max 8 | reader processes for step 1 |
| `--batch` | 400 | rulings per database commit |
| `--actor` | `ingest` | name recorded in the audit log |
| `--dry-run` | off | read and count, write nothing |

### `classify_rulings.py` — step 2 on its own

Same `--provider` / `--model` / `--workers` / `--batch` / `--dry-run`, plus:

| flag | default | what it does |
|---|---|---|
| `--limit` | all | stop after this many rulings |
| `--vocab` | 60 | how many of a chamber's subjects are offered to the model |

### The rest

| script | flags |
|---|---|
| `backfill_themes.py` | `--all` re-read every ruling · `--dry-run` · `--batch` |
| `approve_subjects.py` | `review` or `apply` |
| `reconcile_proposals.py` | `--dry-run` |
| `sync_enrichment.py` | `export <file>` or `apply <file>` |
| `migrate_search_tsv.py` | `--batch` |

---

## Choosing a model

Every setting lives in **`platform/.env`** — copy `platform/.env.example`, which
documents all 27 fields with their defaults. The scripts read it automatically; inside
Docker, compose's environment wins instead.

| provider | key | get one at | notes |
|---|---|---|---|
| `gemini` *(default)* | `GEMINI_API_KEY` | aistudio.google.com | measured: 16,585 rulings, 8 failures, **$4.85**, 35 min |
| `openrouter` | `OPENROUTER_API_KEY` | openrouter.ai/keys | ~1.8× the price of calling Gemini directly |
| `opencode` | `OPENCODE_API_KEY` | opencode.ai/auth | 87 models; needs credit on the account |

```bash
python ingest.py ../../results                                     # Gemini
python ingest.py ../../results --provider opencode --model gemini-3.5-flash-lite
python ingest.py ../../results --no-model                          # no model at all
```

**Gemini is the default on evidence, not preference.** It is the only one measured on
this corpus, and these are court rulings, so a provider you can name and hold to terms
matters more than a few cents.

### OpenCode's free models cannot be used here

`space-bunny-free` and eleven other `-free` ids answer, with a valid key:

```
403  OpenCode's free tier can only be used from within OpenCode
```

They are reserved for the OpenCode terminal app. A key does not change it — tested.
The way to tell this apart from a billing problem: a **paid** id on an account with no
credit answers `402 Insufficient account funds`, and a bad key answers `401`. Three
different errors, three different causes.

A run that hits the 403 stops after the first batch and says so, rather than sending
the same refused request 16,585 times.

---

## The other scripts

| script | when |
|---|---|
| `ingest.py` | **the one you want** — a new delivery |
| `backfill_themes.py` | re-derive subject, rule and outcome from text already stored, after the parser improves. Never overwrites a model-written subject. |
| `classify_rulings.py` | the model step alone, if you want to run it separately |
| `reconcile_proposals.py` | fold proposed subjects back in where they were ours all along under a different spelling (`دعوى إفراغ` → `دعوى الإفراغ`) |
| `approve_subjects.py` | rule on the subjects a model suggested, and file the rulings under what you approve |
| `sync_enrichment.py` | carry the derived fields to another copy of the database instead of paying to compute them twice |
| `migrate_search_tsv.py` | one-time: add the word-search column to a database already serving |
| `backup.sh` · `restore.sh` | the database and the documents |

---

## Approving proposed subjects

A model that cannot find a fitting subject proposes one. Those are **never** adopted —
the ruling keeps its summary and gets no subject until a person rules on it. A legal
taxonomy is not something a model gets to extend on its own.

```bash
python approve_subjects.py review     # writes data/subject_review.json
#   ...open it, set "approve" to true or false, and rename anything spelled badly...
python approve_subjects.py apply      # files the rulings under what you approved
```

The review list is as short as it can honestly be: spellings of one another are merged
under the commonest, anything the court already uses has been filed by
`reconcile_proposals.py` and never appears, and what remains is sorted by how many
rulings turn on it. 773 waiting rulings became 590 decisions, of which 12 cover 99
rulings and the rest are long tail.

Each entry is editable, which matters because the OCR is imperfect:

```json
{ "key": "...", "approve": true, "label": "واجبات الكراء",
  "rulings": 22, "chambers": {"مدنية": 21, "تجارية": 1},
  "also_spelled": ["وجبات الكراء"] }
```

That one is a real example: the model read `وجبات الكراء` — *meals*, not *dues* — off a
scan, 22 times. Approving it under the correct spelling folded those rulings into the
subject the court actually uses. Set `approve` to `false` and the rulings simply keep
no subject, which is the honest outcome for a suggestion that is not a real category.

`apply` never overwrites a subject a ruling already has, and leaves undecided ones
waiting, so you can work through the list over several sittings.

---

## Environment

Settings go in **`platform/.env`** — one file, read automatically by every script
here. Copy `platform/.env.example` to start. Inside Docker the environment comes from
compose instead and always wins, so the same files work in both places.

```bash
# platform/.env
DB_DIR=../../data/platform            # SQLite, for development
DATABASE_URL=postgresql+psycopg://…   # or Postgres, which production uses
FILESTORE_DIR=../../data/platform/files

GEMINI_API_KEY=…                      # step 2, the default provider
OPENROUTER_API_KEY=…                  # step 2, only if --provider openrouter
```

Neither key is needed for step 1. `--no-model` skips step 2 entirely and nothing
leaves the machine.

Nothing under `data/`, `results/`, `lastinput/` or any `.env` is ever committed — the
raw deliveries hold real names.
