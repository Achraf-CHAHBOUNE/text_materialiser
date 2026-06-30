# Arabic Document PII Anonymizer

Extracts text from Arabic legal documents, replaces all personal information (PII)
with `XXXXXXX`, classifies each file into its court chamber, and writes the result
as an editable RTL Word `.docx`.

## Supported inputs (same criteria for all)

| Input                                        | How text is obtained                         | LLM does             | Relative cost              |
| -------------------------------------------- | -------------------------------------------- | -------------------- | -------------------------- |
| **Scanned PDF** (image, no text layer) | vision**OCR** by the model             | OCR + PII + classify | higher (outputs full text) |
| **Text PDF** (has a text layer)        | extracted**locally** (`pypdf`)       | PII + classify only  | low                        |
| **.docx**                              | extracted**locally** (`python-docx`) | PII + classify only  | low                        |

A PDF is auto-detected as scanned vs. text by its embedded text density
(`TEXT_PDF_MIN_CHARS_PER_PAGE` in `anonymizer/loaders.py`). Output is always an
anonymized `.docx` plus a row in `index.csv`, regardless of input type.

## Pipeline

```
scanned PDF
   │  (split into page-batches so each response fits the output-token limit)
   ▼
vision LLM (Gemini)  ──►  { pages: ["…OCR…"], pii: [{text,type}, …] }   # OCR + detect only
   │
   ▼
local redactor (Python)  ──►  replace every PII string with XXXXXXX (+ audit log)
   │
   ▼
.docx writer (RTL Arabic, page breaks)  ──►  output/<name>.docx
```

The LLM **only OCRs and flags PII**; all replacement happens locally in Python.

## Project layout

```
arabic-pii-anonymizer/
├── anonymizer/                  # the package
│   ├── __init__.py              # public API: Pipeline, Settings
│   ├── __main__.py              # enables `python -m anonymizer`
│   ├── cli.py                   # argparse CLI
│   ├── config.py                # .env-driven settings + cost estimate
│   ├── pipeline.py              # orchestration: concurrency, resume, progress, isolation
│   ├── core/                    # domain logic
│   │   ├── categories.py        #   court-chamber taxonomy (classification)
│   │   ├── redactor.py          #   local PII -> XXXXXXX (line-wrap safe)
│   │   └── state.py             #   resume checkpoint + index.csv export
│   ├── documents/               # document I/O
│   │   ├── loaders.py           #   discover .pdf/.docx, auto scan-vs-text batches
│   │   └── docx_writer.py       #   RTL Arabic .docx output
│   ├── llm/                     # pluggable providers
│   │   ├── base.py              #   DocumentAI interface + data classes
│   │   ├── prompt.py            #   OCR/PII/classification prompts
│   │   ├── gemini.py            #   Gemini (process_pdf = OCR; process_text = text)
│   │   └── factory.py           #   PROVIDER -> implementation
│   └── utils/
│       └── logging.py           #   UTF-8 console logging
├── tests/                       # offline unit tests (pytest)
│   └── test_redactor.py
├── input/                       # put PDFs/DOCX here  (contents gitignored)
├── output/                      # results: <name>.docx + index.csv  (gitignored)
├── main.py                      # thin entry shim -> anonymizer.cli
├── pyproject.toml               # packaging + `anonymize` console script
├── requirements.txt
├── environment.yml              # conda env
├── .env.example                 # config template
├── .gitignore
├── LICENSE
└── README.md
```

## Setup

```bash
# option A: plain
pip install -r requirements.txt

# option B: as an installed package (adds the `anonymize` command)
pip install -e .

# option C: conda
conda env create -f environment.yml && conda activate arabic-anonymizer

cp .env.example .env        # then edit .env and set GEMINI_API_KEY
```

Get a Gemini API key: https://aistudio.google.com/apikey

## Run

Three equivalent entry points:

```bash
python main.py                 # thin shim
python -m anonymizer           # module entry
anonymize                      # console script (after `pip install -e .`)
```

Common options (apply to any entry point):

```bash
python -m anonymizer --limit 3       # small batch first (verify cost & quality)
python -m anonymizer --overwrite     # redo everything, ignoring resume state
python -m anonymizer --workers 8 --batch-size 4
```

Output `.docx` files mirror the input folder structure under `OUTPUT_DIR`
(default `output/`).

## Tests

```bash
pip install -e ".[dev]"   # installs pytest
pytest                    # offline unit tests (no API calls)
```

## Category index (side output)

Each document is also **classified** into its court chamber (the black-text category
from the reference taxonomy in `anonymizer/categories.py`) in the same LLM call.
After every run, `OUTPUT_DIR/index.csv` is written (UTF-8 BOM, Excel-ready):

| file       | category                      | court                 | pages | pii_count |
| ---------- | ----------------------------- | --------------------- | ----- | --------- |
| 2021_1_4_0 | الغرفة الإدارية | محكمة النقض | 2     | 13        |

`category` is always one of the black-text chambers; `court` is the parent (blue header)
kept for context. Undetermined documents get `غير محدد`.

## Configuration (`.env`)

| Key                                            | Meaning                      | Default                    |
| ---------------------------------------------- | ---------------------------- | -------------------------- |
| `PROVIDER`                                   | LLM provider                 | `gemini`                 |
| `GEMINI_API_KEY`                             | API key                      | —                         |
| `MODEL`                                      | Model id                     | `gemini-2.5-flash-lite`  |
| `INPUT_DIR` / `OUTPUT_DIR`                 | Folders                      | `input` / `output`     |
| `STATE_FILE`                                 | Resume checkpoint            | `.anonymizer_state.json` |
| `PAGES_PER_BATCH`                            | Pages per LLM call           | `5`                      |
| `MAX_WORKERS`                                | Parallel documents           | `4`                      |
| `REPLACEMENT_TOKEN`                          | What PII becomes             | `XXXXXXX`                |
| `INPUT_PRICE_PER_M` / `OUTPUT_PRICE_PER_M` | For cost report (USD/1M tok) | `0.10` / `0.40`        |

## Cost

Roughly **$0.0004–0.0009 per page** with Gemini 2.5 Flash-Lite (output text dominates).
Scales linearly with page count. The run prints **real** token usage and an estimated
cost from the API's reported tokens.

## Resume & errors

- Every finished document is recorded in `STATE_FILE`; rerunning skips completed work.
- A document that errors is logged and marked `failed` — the run continues; rerun to retry.
- Each redaction is auditable: replaced values are counted, and any PII the model flagged
  but that couldn't be matched in the text is logged as a warning.

## Switching LLM provider

Implement `DocumentAI` (see `anonymizer/llm/base.py`) in a new module under
`anonymizer/llm/`, register it in `factory.get_provider`, then set `PROVIDER` in `.env`.
A hybrid **self-hosted OCR + cheap PII detector** fits the same interface — useful at high
volume or when documents must not leave your infrastructure.

```
```

## Limitations

- Output is reflowed paragraph text (RTL, page breaks) — **not** a pixel-perfect copy of
  the scan's table/column layout.
- OCR is excellent but not perfect on poor scans; an LLM can also miss a PII item.
  For legal/privacy use, spot-check using the audit log.
