# Project 1 — Brief

**Anonymization & extraction of Moroccan court decisions — 2,000 files (`.doc`, `.docx`, `.pdf`, images)**

> Defines **what** must be achieved. The method is yours to design and justify.

---

## Flow

```
   ┌──────────────┐
   │ 2,000 files  │  .doc · .docx · .pdf · images
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │     READ     │   whatever the format, get the text
   └──────┬───────┘
          │
          ├─────────────┬─────────────┬──────────────┐
          ▼             ▼             ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐
    │  FIELDS  │  │ CATEGORY │  │ RELATION │  │  DETECT    │
    │ رقم القرار│  │  إدارية  │  │ استئناف  │  │ personal   │
    │ رقم الملف │  │  تجارية  │  │    ↓     │  │   data     │
    │  التاريخ  │  │   ...    │  │  النقض   │  │            │
    └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘
         │             │             │              │
         └─────────────┴──────┬──────┴──────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      ┌───────────────┐              ┌────────────────┐
      │  JSON record  │              │  SAFE  file    │
      │  (metadata)   │              │  same format,  │
      │      /xlsx    │              │  no personal   │
      └───────────────┘              │  data          │
                                     └────────┬───────┘
                                              │
                                              ▼
                                     ┌────────────────┐
                                     │  LEAK  TEST    │  ← release gate
                                     │  0 hits or     │
                                     │  rejected      │
                                     └────────────────┘
```

**Order matters:** extraction runs on the original text. Anonymization writes to a copy.

---

## 1. What to build

| # | Feature             | Requirement                                                                                                                                                                                             |
| - | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | **Anonymize** | No name, address, ID number, or contact detail of a private person survives — anywhere in the file, not just on screen. Court, chamber, reasoning, laws, amounts, numbers and dates are**kept**. |
| 2 | **Extract**   | `رقم القرار` · `رقم الملف` · `تاريخ القرار` — with confidence and source. filename                                                                                 |
| 3 | **Classify**  | إدارية · تجارية · مدنية · جنائية · اجتماعية · أحوال شخصية · عقارية · غير محدد.                                                             |
| 4 | **Link**      | `استئناف ← نقض` — the referenced decision (court, number, date, file no.), linked when both are in the corpus. Design must extend to 3 levels later.                                      |

`غير محدد` is fine. A confident wrong answer is not. A missing link is fine. A **wrong** link is not.

---

## 2. Rules

- **Idempotent** — same input, same output, every run.
- **Resumable** — crash at file 1,700 ≠ restart from 0.
- **Fault-isolating** — a bad file is quarantined with a reason, never kills the batch.
- **Auditable** — for every field extracted and every element removed: where it came from, what decided it.
- **Configurable** — thresholds, budgets, models, policy in config, not code.
- **Containerized** — runs on a clean machine, one command.
- The corpus is inconsistent across years. Robustness is part of the evaluation.

---

## 3. Cost

1. Every paid call metered and logged — calls, tokens, cost — per file and total.
2. Run report states **measured cost per file** and **projected total for 2,000**.
3. Hard budget ceiling: reaching it **halts** the run.
4. **Dry run on real files before any full run.** No full run without that number.
5. Be ready to explain why your cost is what it is, and what the cheaper option was. Reducing paid calls is an explicit design goal and will be evaluated.

---

## 4. Quality targets

| Metric                                                                         | Target          |
| ------------------------------------------------------------------------------ | --------------- |
| Personal data —**nothing missed** (recall)                              | ≥ 99.5%        |
| Personal data — nothing over-removed (precision)                              | ≥ 95%          |
| `رقم القرار` / `رقم الملف` / `الملفالتاريخ` | ≥ 99% each     |
| Category                                                                       | ≥ 98%          |
| Relation — precision / recall                                                 | ≥ 98% / ≥ 90% |
| Quarantined files                                                              | < 2%            |

Report **by format and by chamber**, not just a global average.

**Release gate:** an automated search of every delivered output for known personal data must return **zero** hits. Absolute.

---

## 5. Deliver before coding — Technical Design Document (5–10 pages)

1. **Corpus audit** — what you actually found in the 2,000 files. Real numbers. Do this first.
2. Approach for each of the 4 features, and why.
3. **Where AI is used and where it isn't** — justify each use.
4. **Cost estimate** for 2,000, how you got it, how you reduce it.
5. **What your approach will get wrong**, and how you'll detect it.
6. Test strategy.
7. Output schema proposal.
8. Plan and milestones.

Reviewed before production code starts. I'm evaluating the reasoning as much as the result.

---

## 6. Testing

- Split the 2,000 and justify the split. Part must be **manually annotated ground truth**; part stays **untouched until acceptance**.
- Annotation is part of the work — plan it from day 1.
- **Accuracy measured on data you tuned on will not be accepted.**
- Automated, re-runnable, in CI. Deliver a harness I can run myself to get the §4 table.
- Also test: damaged / empty / unusual files · outputs open correctly in their native app · repeated runs identical · no recoverable personal data by any means.


---

## 7. Deliverables

Design document → working CLI → config file → container → tests + evaluation harness → run report (metrics, cost, quarantine list) → docs stating what is removed, what is kept, and where any sensitive by-product is stored.
