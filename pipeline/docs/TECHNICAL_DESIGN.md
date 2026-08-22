# Project 1 — Technical Design Document

**Anonymization & extraction of Moroccan court decisions**
Pipeline that turns raw `.doc`/`.docx`/`.pdf`/image files into anonymized files + structured metadata.

Brief: [`../../Script.md`](../../Script.md). This document is delivered for review **before**
production hardening, per §5. It states what we found, how we will build each feature, where AI
is and isn't used, the cost and how we cut it, what we expect to get wrong, how we test, the
output schema, and the plan.

> **Status of the numbers below.** The audit in §1 is run on the **26-file sample** currently in
> hand. The full 2,000-file audit is the first production task and *gates* the full run (§3.4).
> Every quantitative claim marked _(sample)_ is measured on those 26 files; every one marked
> _(projected)_ is extrapolated and will be replaced by a measured dry-run number before any full run.

---

## 1. Corpus audit

### 1.1 What we actually have _(sample, 26 files)_

| Format        | Count | Notes |
| ------------- | ----- | ----- |
| `.doc` (legacy binary) | 21 | `2021_1_4_*` series — محكمة النقض, الغرفة الإدارية, year 2021. Digital text (not scans). |
| `.docx`       | 5     | incl. real appeal→cassation pair (`3646_appel`, `652_Cassation`) and a synthetic 3-level linkage triple (`ibtidai_12345`, `istinaf_1990`, `naqd_589-3`). |
| `.pdf` (text) | 0     | **not yet in the sample** — expected in the full corpus. |
| `.pdf` (scan) / image | 0 | **not yet in the sample** — expected in the full corpus. |

Observed characteristics that drive the design:

- **Text is often inside Word text boxes**, not paragraphs. `3646_appel` and `652_Cassation`
  return **0 characters** from `document.paragraphs`; the body lives in drawing text boxes. The
  loader must walk the full XML tree for every `<w:p>` (incl. text boxes) and skip `mc:Fallback`
  duplicates. This is already implemented and is the single most important robustness fix so far.
- **Legacy `.doc`** cannot be read by `python-docx`; it needs LibreOffice headless
  (`soffice --convert-to docx`) as a first step.
- **PII appears with and without honorifics** and can be **line-wrapped**, so exact-string
  redaction leaks. Redaction must be whitespace-flexible, Arabic-variant tolerant, and strip
  honorific prefixes (السيد / الأستاذ …) before matching.
- **The corpus is inconsistent across years** (§2). The sample is a single chamber/year and is
  therefore *not* representative of the 2,000 — we must not tune thresholds on it (§6).

**Measured audit of the sample** (via `python -m anonymizer.audit`, deterministic, no LLM):
26 files → **21 `.doc` + 5 `.docx`**, **0% scanned** (all digital text), **0 empty / 0 damaged**,
**1 duplicate** (`2021_1_4_12 copy.doc` = `2021_1_4_12.doc`), chamber by header keyword
**23 إدارية + 3 تجارية**. The single sample chamber/year confirms §6: we must not tune on it.

### 1.2 The full-corpus audit (first production task)

The same tool (`anonymizer/audit.py`) runs on the 2,000 files to produce the real numbers:
counts by **format** and by **chamber/year**; the **scanned vs. text** ratio (dominates cost);
empty/damaged files; and **duplicates** (content hash). It writes `audit_report.md/.json` and is
the first thing to run on the delivered corpus — before any paid call.

---

## 2. Approach per feature

Order matters: **extraction and classification run on the original text; anonymization writes to a
copy** (Script.md flow). We never extract from the redacted text.

### 2.1 Read (format → text)
- `.doc` → LibreOffice headless → `.docx` → text-box-aware extraction.
- `.docx` → text-box-aware extraction directly.
- **text** `.pdf` → embedded-text extraction (no LLM).
- **scanned** `.pdf` / image → LLM **vision OCR** (the only step that needs a vision model).
- A cheap classifier decides text-PDF vs. scan: if embedded text density is above a threshold,
  treat as text and skip OCR (a direct cost lever, §4).

### 2.2 Extract (`رقم القرار`, `رقم الملف`, `تاريخ القرار`)
- **Deterministic regex first** (Arabic + ASCII digits, tatweel/diacritic tolerant) — free, and
  auditable. Each hit records its **source span** and a **confidence**.
- **LLM fills only what regex missed or flagged low-confidence.** Values are reconciled; on
  conflict the higher-confidence source wins and the disagreement is logged for the work queue.
- Target ≥99% each (§4) → every field carries confidence + source so low-confidence ones surface
  for review rather than shipping a confident wrong answer.

### 2.3 Classify (chamber)
- Fixed label set: إدارية · تجارية · مدنية · جنائية · اجتماعية · أحوال شخصية · عقارية · غير محدد.
- Strong **lexical priors** (chamber name / court header regex) resolve most cases for free;
  the LLM decides only the ambiguous remainder. **`غير محدد` is a valid answer** — we never force
  a guess (§ brief: a confident wrong answer is worse than `غير محدد`).

### 2.4 Link (`استئناف ← نقض`, extensible to 3 levels)
- Each decision emits a **case-identity key** (court, decision no., file no., date) and any
  **references** it makes to a prior decision.
- A small graph DB (documents + refs + edges) links a reference to a target **only on a strong
  match** — exact file-number match, or (decision no. + date + court). Connected components get a
  `case_id`. **Only high/medium-confidence edges auto-link;** weak matches are left for review.
- Design is **arrival-order independent**: cassation can arrive months before its appeal; the edge
  is created whenever the second document lands. Extends to ابتدائي→استئناف→نقض by adding levels,
  not by rewriting the matcher.
- Governing rule: **a missing link is acceptable; a wrong link is not** (§4 precision ≥98%).

### 2.5 Anonymize (write to a copy)
- Local, deterministic redaction over the extracted PII list: whitespace-flexible,
  Arabic-variant-tolerant, honorific-stripping. Output keeps the **same format** as the input.
- **Kept:** court, chamber, reasoning, laws, amounts, numbers, dates. **Removed:** names,
  addresses, ID numbers, contact details of private persons.

### 2.6 Leak-test (release gate)
- After writing, an automated pass re-reads the **output** and searches for every known PII string
  (and normalized variants) extracted in §2.2/§2.5. **Zero hits or the file is rejected/quarantined.**
  This is the absolute gate of §4 and is enforced in code, not by inspection.

---

## 3. Where AI is used — and where it is not

| Step | AI? | Why |
| ---- | --- | --- |
| `.doc`/`.docx`/text-PDF reading | **No** | Deterministic parsing is exact and free. |
| Scan/image OCR | **Yes (vision)** | No reliable non-Chinese, non-GPU OCR for Arabic legal scans at this budget. |
| Field extraction | **Regex first, AI fallback** | Regex is auditable and free; AI only for the residue. |
| Classification | **Priors first, AI on ambiguous** | Most headers are lexically decidable. |
| PII detection | **Yes** | Recall ≥99.5% needs semantic understanding regex can't reach. |
| Redaction (removal) | **No** | Local string replacement — deterministic, idempotent, auditable. |
| Linkage | **No** | Graph matching on extracted keys; explainable, no model. |
| Leak-test | **No** | A search must be exhaustive and deterministic, never probabilistic. |

Principle: **AI reads and understands; deterministic code decides, removes, links, and verifies.**
Every AI use is justified above; everything that must be reproducible or auditable is code.

---

## 4. Cost estimate & reduction

**Model:** Gemini 2.5 Flash-Lite — cheapest capable model with native Arabic + PDF/vision, within
budget (input ≤ $0.50 / output ≤ $1.00 per 1M; actual $0.10 / $0.40 per 1M).

**Per-file _(sample, text `.doc`)_:** one call (extract + classify + PII + identity) ≈ 4k input +
1.5k output tokens ≈ **$0.001/file**. Scanned pages add vision tokens — projected **2–4×**.

**Projected 2,000 files:** ≈ **$2 (all-text)** to **≈ $8 (all-scan)**. Well inside a $300 trial.
_These are projections; the §3.4 dry run replaces them with a measured number before the full run._

**How cost is governed (Script.md §3):** every paid call meters calls/tokens/cost, per file and
total; the run report states measured cost/file and projected total; a **hard budget ceiling halts
the run**; **a dry run on real files is mandatory before any full run.**

**Reduction levers (explicit design goal):** skip OCR for text PDFs; regex/priors before every LLM
call; one combined call per document instead of four; batch pages; cache by content hash so a
re-run (or a duplicate file) costs nothing.

---

## 5. What this will get wrong — and how we detect it

| Failure | Detection |
| ------- | --------- |
| PII missed (recall miss) | **Leak-test gate** re-scans output; ground-truth recall on the held-out annotated set. |
| Over-redaction (a law/amount removed) | Precision measured on ground truth; kept-terms allow-list checked. |
| Wrong field value read confidently | Confidence + source on every field; low-confidence → work queue, not shipped. |
| **Wrong link** (worse than none) | Only strong-match edges auto-link; everything else is left unlinked for review. |
| OCR garbling rare glyphs / old scans | Text-density & confidence checks; low-confidence pages quarantined, batch continues. |
| Damaged / empty / unusual file | Fault isolation: quarantined with a reason, never kills the batch (§2 rules). |

---

## 6. Test strategy

- **Split the 2,000** into a **manually annotated ground-truth set** and an **untouched acceptance
  set** held until acceptance. Accuracy measured on data we tuned on is not accepted.
- **Annotation planned from day 1** — it is part of the work.
- **Automated, re-runnable, CI harness** that emits the §4 metrics table **by format and by
  chamber**, not just a global average.
- Adversarial fixtures: damaged/empty/unusual files; outputs must open in their native app;
  **repeated runs byte-identical** (idempotence); **no personal data recoverable by any means**.

---

## 7. Output schema (proposal)

Per document, a JSON record (aggregated to XLSX for the client hand-off):

```json
{
  "doc_id": "652_Cassation",
  "source_file": "652_Cassation.docx",
  "format": "docx",
  "read_method": "docx-textbox",
  "fields": {
    "رقم القرار": { "value": "652", "confidence": 0.98, "source": "regex:header" },
    "رقم الملف":  { "value": "1293/8222/2017", "confidence": 0.95, "source": "llm" },
    "تاريخ القرار": { "value": "2018-12-12", "confidence": 0.9, "source": "regex" }
  },
  "category": { "value": "تجارية", "confidence": 0.97 },
  "level": "نقض",
  "case_id": "C-1293/8222/2017",
  "links": [ { "to": "3646_appel", "relation": "استئناف←نقض", "confidence": "high" } ],
  "pii": { "removed_count": 3, "types": ["name","name","lawyer"] },
  "anonymized_file": "652_Cassation.docx",
  "leak_test": { "passed": true, "hits": 0 },
  "cost": { "calls": 1, "input_tokens": 4102, "output_tokens": 1490, "usd": 0.0010 },
  "audit": { "run_id": "...", "model": "gemini-2.5-flash-lite", "timestamp": "..." }
}
```

A **run report** accompanies the batch: per-file + total cost, the §4 metrics table, and the
quarantine list with reasons.

---

## 8. Plan & milestones

| # | Milestone | Exit criterion |
| - | --------- | -------------- |
| 0 | **This TDD reviewed** | Sign-off before production hardening. |
| 1 | Full corpus audit (§1.2) | Real format/chamber numbers; scan ratio; dry-run cost. |
| 2 | Ground-truth annotation set | Agreed split; annotated held-out set exists. |
| 3 | JSON/XLSX output schema (§7) | Schema emitted for every sample file. |
| 4 | Leak-test gate + quarantine + budget ceiling | Gate rejects any PII; budget halts the run; bad files isolated. |
| 5 | Idempotent + resumable run | Re-run byte-identical; crash at N resumes at N. |
| 6 | Containerized CLI (one command) | `docker run … --input --output` produces safe files + report. |
| 7 | Evaluation harness in CI (§6) | Client can run it to reproduce the §4 table by format & chamber. |
| 8 | Dry run on real files → full run | Measured cost approved; full run within budget; zero leak hits. |

---

### Current build vs. this plan

Already implemented: format reading (incl. text-box `.docx` and legacy `.doc`), regex+LLM
extraction, classification with priors, strong-match graph linkage (arrival-order independent),
local variant-tolerant redaction, per-call cost metering, resumable state.

**Landed (milestones 3–4):**
- JSON + XLSX output schema (§7) — `records.json`, `records.xlsx` with per-field value/confidence/source.
- **Leak-test release gate** — re-scans every *delivered* file; a survival quarantines the file out
  of the clean output dir (two-pass matcher, broader than the redactor). Proven by a test where a
  diacritic name the redactor misses is caught by the gate.
- **Hard budget ceiling** (`--budget` / `BUDGET_USD`) — the run halts when reached.
- **Quarantine flow** — leaked + failed files listed in `quarantine.csv`; run report in
  `run_report.md`/`.json` with measured cost/file and projected total; `--dry-run` cost probe.

**Landed (milestones 5–7):**
- **Idempotence** — the anonymized `.docx` is byte-identical across re-runs (constant zip
  timestamps + static core.xml); proven by `test_idempotent.py`.
- **Evaluation harness** — `python -m anonymizer.evaluate --truth truth.json --output output/`
  scores a run against ground truth and prints the §4 table **by format and by chamber**
  (`evaluate.py`, `test_evaluate.py`).
- **Container + CI** — pipeline `Dockerfile` + `.dockerignore` (CLI entrypoint); GitHub Actions
  runs the whole suite on every push (`.github/workflows/ci.yml`).
- **Category taxonomy** aligned to the briefs' short labels (إدارية/تجارية/… ) with tolerant mapping.

- **Corpus audit tool** (`anonymizer/audit.py`) — deterministic profiler (milestone 1);
  measured on the sample in §1.1. Verified in a clean venv (mirrors the Docker image):
  fresh `pip install -r requirements.txt` + CLI + audit all run.

**Remaining for Project 1 (externally blocked, not code):** the measured **cost dry-run**
(`--dry-run`) needs the Gemini API key, and the **live `docker build`/run** needs the Docker
daemon. The full-corpus audit runs the tool above on the 2,000 files once delivered.
Everything else in the plan is implemented and tested (21 tests).
