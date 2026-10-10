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

## Options

```bash
python ingest.py ../../results --no-model      # free; nothing leaves this machine
python ingest.py ../../results --dry-run       # read and count, write nothing
python ingest.py ../../results --workers 6     # default: cores, capped at 8
python ingest.py ../../results --no-publish    # import for review instead of live
```

### Choosing a model

```bash
python ingest.py ../../results                                    # Gemini (default)
python ingest.py ../../results --provider openrouter --model x-ai/grok-4.3
```

| | |
|---|---|
| `--provider gemini` | needs `GEMINI_API_KEY` (or `TRANSLATE_API_KEY`) |
| `--provider openrouter` | needs `OPENROUTER_API_KEY` |

**Gemini 2.5 Flash-Lite is the default, deliberately.** It is the only model measured
on this corpus — 16,585 rulings, 8 failed calls, **$4.85**, 35 minutes — and it comes
from a provider you can name and hold to terms. That last point is not a detail: these
are court rulings. Anonymous or "stealth" models are cheaper to reach for and
impossible to audit; you cannot check where the data goes, how long it is kept, or
whether it trains someone's model, and they disappear without notice, which breaks a
pipeline you intend to re-run. The flag exists so this is your choice, not a lock-in.

---

## The other scripts

| script | when |
|---|---|
| `ingest.py` | **the one you want** — a new delivery |
| `backfill_themes.py` | re-derive subject, rule and outcome from text already stored, after the parser improves. Never overwrites a model-written subject. |
| `classify_rulings.py` | the model step alone, if you want to run it separately |
| `reconcile_proposals.py` | fold proposed subjects back in where they were ours all along under a different spelling (`دعوى إفراغ` → `دعوى الإفراغ`) |
| `sync_enrichment.py` | carry the derived fields to another copy of the database instead of paying to compute them twice |
| `migrate_search_tsv.py` | one-time: add the word-search column to a database already serving |
| `backup.sh` · `restore.sh` | the database and the documents |

---

## Approving proposed subjects

A model that cannot find a fitting subject proposes one. Those are **not** adopted:

```
data/proposed_subjects.json
  [{ "doc_id": "...", "chamber": "جنائية", "proposed": "تسليم المجرمين" }]
```

Review them, then re-run `reconcile_proposals.py`. Anything genuinely new is yours to
add to the vocabulary deliberately — which is the point: the taxonomy is the court's
words plus what you approve, never what a model decided on its own.

---

## Environment

```bash
DB_DIR=../../data/platform          # SQLite, for development
DATABASE_URL=postgresql+psycopg://…  # or Postgres, which production uses
FILESTORE_DIR=../../data/platform/files
GEMINI_API_KEY=…                     # only needed for step 2
```

Nothing under `data/`, `results/`, `lastinput/` or any `.env` is ever committed — the
raw deliveries hold real names.
