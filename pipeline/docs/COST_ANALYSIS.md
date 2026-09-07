# Cost Analysis — measured on 20 real documents

**Test date:** 2026-09-02 · **Model:** `gemini-2.5-flash-lite` · **Corpus:** `01_civile` (real scanned Moroccan cassation rulings)

This is a **real run on 20 real documents**, not an estimate. Every number below was measured.

---

## 1. Headline result

| Metric | Value |
| ------ | ----- |
| Documents processed | **20** |
| Pages processed | **74** (avg 3.7 pages/doc) |
| PII items removed | **209** |
| **Total cost** | **$0.0545** |
| **Average cost / document** | **$0.00273** |
| **Median cost / document** | **$0.00094** |
| Average cost / page | $0.00074 |
| Wall time | 145 s (~2.5 min) with 10 parallel workers |
| Quarantined (bad scans) | 2 of 20 (10%) |

> **Note the gap between average ($0.00273) and median ($0.00094).**
> That gap is the whole story — see §4.

---

## 2. How you are charged

Google bills **per token**, split into input and output. There is no per-document or per-page fee.

| Token type | Rate (per 1M tokens) | What it is here |
| ---------- | -------------------- | --------------- |
| **Input** | $0.10 | The instruction + the scanned page images we send |
| **Output** | $0.40 | The text the model writes back (the OCR transcription + detected PII + metadata) |
| **Cached input** | $0.01 (90% off) | The instruction, re-used across documents |

**Cost of one document = (input tokens x $0.10 + output tokens x $0.40) / 1,000,000**

### Why output dominates
Output is **4x more expensive** than input, and for scanned documents the model must **transcribe every page**, so output is large.

Measured average per document: **5,780 input tokens / 5,368 output tokens**.
So roughly **70% of every bill is the output** (the transcription), not the input.

This matters: *sending* the scan is cheap; *reading it back as text* is what costs.

---

## 3. Per-document breakdown (all 20, most expensive first)

| Document | Pages | Input tok | Output tok | Cost |
| -------- | ----: | --------: | ---------: | ---: |
| administrative_2023-01-17_2023_36 ⚠️ | 4 | 11,827 | **65,524** | **$0.02739** |
| civile_2005-03-09_2005_738 ⚠️ | 14 | **60,307** | 4,162 | **$0.00770** |
| civile_2008-12-17_2008_4302 | 7 | 3,682 | 6,530 | $0.00298 |
| civile_2013-07-02_2013_392 | 5 | 2,228 | 5,164 | $0.00229 |
| 1976_777_1976-12-15 | 7 | 3,682 | 4,229 | $0.00206 |
| civile_2015-04-21_2015_246 | 3 | 1,712 | 3,315 | $0.00150 |
| civile_2014-12-16_2014_621 | 3 | 1,712 | 3,054 | $0.00139 |
| ch1_2022_715 | 3 | 1,712 | 2,505 | $0.00117 |
| administrative_2022-02-03_2022_303 | 2 | 1,454 | 2,101 | $0.00099 |
| administrative_2022-03-01_2022_177 | 2 | 1,454 | 1,976 | $0.00094 |
| administrative_2022-04-19_2022_503 | 2 | 1,454 | 1,919 | $0.00091 |
| civile_2011-08-09_2011_3288 | 2 | 1,454 | 1,606 | $0.00079 |
| 2017_2_2017-01-03 | 3 | 2,964 | 936 | $0.00067 |
| ch3_2024_682 | 3 | 3,585 | 586 | $0.00059 |
| civile_2016-02-09_2016_82 | 2 | 2,932 | 723 | $0.00058 |
| ch1_2024_75 | 2 | 3,335 | 591 | $0.00057 |
| ch1_2024_113 | 2 | 2,731 | 702 | $0.00055 |
| 2017_190_2017-03-21 | 3 | 2,696 | 621 | $0.00052 |
| administrative_2022-03-24_2022_253 | 3 | 2,291 | 580 | $0.00046 |
| civile_2017-01-03_2017_1 | 2 | 2,397 | 548 | $0.00046 |
| **TOTAL** | **74** | **115,609** | **107,372** | **$0.0545** |

⚠️ = quarantined by the pipeline as an unreadable scan (output discarded).

---

## 4. The most important finding: **bad scans cost 64% of the money and produce nothing**

| Group | Docs | Total cost | Avg / doc | Share of spend |
| ----- | ---: | ---------: | --------: | -------------: |
| **Clean, delivered** | 18 (90%) | $0.0194 | **$0.00108** | 36% |
| **Bad scans, thrown away** ⚠️ | 2 (10%) | $0.0351 | **$0.01754** | **64%** |

**A single unreadable scan costs 16x an average good document — and its output is discarded.**

Why they explode:
- `administrative_2023-01-17` — a garbled scan made the model emit **65,524 output tokens** (it kept trying to transcribe noise). That one file alone is **50% of the entire 20-document bill**.
- `civile_2005` — a 14-page low-quality scan pushed **60,307 input tokens**.

Both were caught by the quality gate and quarantined, so they cost money **and delivered nothing usable**.

---

## 5. Projection to the full corpus — **51,000 documents**

The client corpus is **51,000 files** (25x the original 2,000 estimate). Extrapolating the
measured per-document costs:

| Scenario | Cost for 51,000 | Notes |
| -------- | --------------: | ----- |
| **As-is** (same 10% bad-scan mix) | **$138.97** | What you would pay running it today |
| &nbsp;&nbsp;↳ *of which wasted on unreadable scans* | *$89.45* | *5,100 documents that produce nothing* |
| Skip bad scans before the API call | **$55.08** | −60% |
| Vertex AI **batch** mode (−50%) | **$69.49** | Same output, half price |
| **Batch + skip bad scans** | **$27.54** | −80% — the target |

**Budget guidance: ~$140 as-is, or ~$28 fully optimised.** Even the worst case is modest —
**cost is not the constraint at this scale. Time and manual review are.**

---

## 6. At 51,000 documents, the real constraints are TIME and REVIEW LOAD

### 6.1 Time — solved by the API key pool

Measured throughput is **~11 documents/minute per API key**. Adding more *local workers* does
not help — the per-key server-side throughput is saturated (verified: 48 workers ran *slower*
than 24). The only lever that scales is **more keys**, and it scales close to linearly because
each key has its own independent throughput budget.

**With an API key pool:**

| Keys in pool | Throughput | Time for 51,000 |
| -----------: | ---------: | --------------: |
| 1 | 11 docs/min | 77 h (3.2 days) |
| 2 | 22 docs/min | 39 h (1.6 days) |
| **4** | 44 docs/min | **19 h (overnight)** |
| **8** | 88 docs/min | **9.7 h (one working day)** |
| 16 | 176 docs/min | 4.8 h |
| 24 | 264 docs/min | 3.2 h |

**A pool of 8 keys turns a 3-day run into a single working day.** With 4 keys it runs overnight.
This removes time as the project constraint.

> **Important: a key pool changes speed, not cost.** The same tokens are billed either way, so
> the ~$139 figure is unchanged. Pool for throughput; use batch mode for price.

**Implementation note:** the pipeline currently reads a **single** `GEMINI_API_KEY`. To use a
pool it needs key-rotation support — either round-robin assignment of keys across worker threads,
or sharding the corpus into N slices and running one process per key (which works today with no
code change). Round-robin pooling inside one process is the cleaner option and is a small change.

### 6.2 Manual review load — the hidden cost
At the measured **10% bad-scan rate**, 51,000 documents produce:

> **~5,100 documents quarantined for manual handling.**

That is the largest real cost in this project, and it is **human time, not API spend**. At even
2 minutes per document, that is ~170 hours of review work. This needs a decision **before** the
run: re-scan them, run a stronger OCR pass, or accept them as excluded.

### 6.3 Storage
| Item | Size |
| ---- | ---- |
| Input PDFs (raw, stays offline) | **~26 GB** |
| Anonymized .docx output | ~2 GB |
| Platform database (metadata + searchable text) | ~0.5 GB |

Nothing here is problematic, but the raw 26 GB must live on the secure machine, never the platform.

---

## 7. Recommendations for a 51,000-document run

1. **Filter unreadable scans before the API call.** Saves ~$89 *and*, more importantly, stops
   ~5,100 wasted API round-trips that also consume hours of runtime.
2. **Use Vertex AI batch mode.** Halves the cost and turns a 3–4 day run into hours. At 51k this
   is the single highest-value change.
3. **Cap output tokens per document.** One garbled file emitted 65,524 output tokens; a ceiling
   scaled to page count bounds the damage.
4. **Decide the bad-scan policy up front** — 5,100 documents is a project in itself.
5. **Run a paid dry-run on ~200 documents first** (~$0.55) to confirm the bad-scan rate holds at
   10% before committing to the full corpus. The 10% figure comes from a 20-document sample;
   on 51,000 files it could plausibly be 5% or 20%, which swings both the bill and the review
   load substantially.

---

## 8. What is *not* charged

- **Anonymization itself is free.** Redaction runs locally with regex — no API cost.
- **Re-running is free for finished documents.** The pipeline is resumable and skips completed work.
- **Leak-test, quality gate, linkage and all reports are local** — zero API cost.
- **The web platform costs nothing per document** — it only serves already-processed files.

---

## 9. Reproducing this measurement

```bash
cd pipeline
python -m anonymizer --dry-run --input <folder> --output <out>
```

Every run writes `run_report.md` / `run_report.json` with measured cost per file and a projected
total; `records.json` holds exact per-document token counts.

**Guardrails:**
- `--budget 50` (or `BUDGET_USD=50`) — hard ceiling; the run halts the moment it is reached.
  **Strongly recommended for a 51,000-document run.**
- `--dry-run` — measure on a real sample before committing.

---

### Summary in one line

**20 real documents cost $0.0545. Scaled to the client's 51,000 files that is ~$139 as-is
(~$28 optimised) — but with an API key pool the binding constraint is no longer time —
it is the ~5,100 unreadable scans needing manual review. A pool of 8 keys runs the whole corpus in
one working day; a bad-scan pre-filter cuts both the bill and that review load.**
