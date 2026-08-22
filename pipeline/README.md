# Project 1 — Anonymization & extraction pipeline

Batch CLI that turns raw Moroccan court decisions (`.doc`, `.docx`, `.pdf`, images)
into **anonymized files + structured metadata**, safe to hand to the web platform.

Brief: [`../Script.md`](../Script.md).

## What it does (per file)

1. **Read** — get the text whatever the format (LibreOffice for legacy `.doc`,
   text extraction for text PDFs/`.docx`, LLM vision OCR for scans/images).
2. **Extract** — `رقم القرار`, `رقم الملف`, `تاريخ القرار` (+ confidence & source).
3. **Classify** — chamber: إدارية · تجارية · مدنية · جنائية · اجتماعية · أحوال شخصية · عقارية · غير محدد.
4. **Link** — `استئناف ← نقض` when both decisions are in the corpus (extensible to 3 levels).
5. **Anonymize** — remove every private-person identifier; keep court, chamber,
   reasoning, laws, amounts, numbers, dates. Written to a *copy*.
6. **Leak-test** — release gate: an automated search of the output for known PII
   must return zero hits.

## Run (local)

```bash
cp .env.example .env          # then put the Gemini key in .env
pip install -r requirements.txt

python -m anonymizer.audit --input input          # 1. audit the corpus (no LLM, no cost)
python -m anonymizer --dry-run --input input      # 2. cost probe on a real sample
python -m anonymizer --input input --output output  # 3. full run
```

Step 1 (`audit`) profiles the folder — format mix, scanned-vs-text ratio, chamber guess,
empty/damaged files, duplicates — and writes `output/audit.md`/`.json`. Do it first.
The optional operator UI is `streamlit run app.py` (`pip install streamlit`).

## Run (container — one command)

```bash
docker build -t court-anonymizer .
docker run --rm --env-file .env \
  -v "$PWD/input:/data/in" -v "$PWD/output:/data/out" \
  court-anonymizer --input /data/in --output /data/out
```

## Configuration

All tunables are environment variables (see [`.env.example`](.env.example)) — model,
budget/prices, paths, workers, replacement token. Nothing is hard-coded in the source.

## Outputs

Written under `output/`:

| File | What |
| ---- | ---- |
| `<doc>.docx` | the anonymized file (same format as input) |
| `_quarantine/<doc>.docx` | files that **failed the leak test** — never delivered clean |
| `records.json` / `records.xlsx` | per-document metadata (fields + confidence/source, category, level, case_id, links, leak result, cost) |
| `run_report.md` / `run_report.json` | measured cost/file, projected total, quarantine summary |
| `quarantine.csv` | every rejected/failed file with a reason |
| `cases.csv` / `documents.csv` / `index.csv` | case linkage + category index |

Raw inputs and everything under `output/` are git-ignored — they must never be committed.

### Cost governance

- `--dry-run` — cost probe on a real sample; reports the projected total for 2,000 **before** any full run.
- `--budget 5` (or `BUDGET_USD`) — hard ceiling; the run halts the moment it is reached.
- Every paid call is metered (calls/tokens/USD) per file and in the run report.

## Layout

```
anonymizer/           the engine (importable package)
  core/               redaction, categories, identifiers, case-linkage DB, run state
  documents/          format loaders, .doc conversion, .docx writer
  llm/                provider abstraction (Gemini), prompt, factory
  pipeline.py         orchestration
  cli.py              command-line entry
tests/                engine tests
input/  output/       local I/O (git-ignored)
```

## Status vs. the brief

Built: read, extract, classify, link, anonymize, cost metering, resumable state,
**JSON/XLSX output, leak-test release gate, hard budget ceiling, quarantine flow**, and the
Technical Design Document ([`docs/TECHNICAL_DESIGN.md`](docs/TECHNICAL_DESIGN.md)).
Remaining: container smoke-test on the real corpus, the CI evaluation harness for the §4
metrics table (by format & chamber), and the idempotence proof. See the TDD milestones.
