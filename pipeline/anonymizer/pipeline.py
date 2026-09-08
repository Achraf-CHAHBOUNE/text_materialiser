"""Orchestration: discover PDFs -> OCR+PII per batch -> redact -> write .docx.

Documents are processed concurrently (API calls are I/O-bound). Each document is
isolated: one failure is logged and skipped, the run continues. Progress and the
resume checkpoint are updated after every document.
"""
from __future__ import annotations

import datetime as _dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .config import Settings
from .core.casedb import CaseDB
from .core.categories import UNKNOWN, normalize_category
from .core.identifiers import Ident, local_extract
from .core.leaktest import leak_scan
from .core.quality import ocr_garbled
from .core.redactor import redact_structured, redact_text
from .core.state import DocRecord, State
from .documents import records as records_mod
from .documents.records import F_DATE, F_DECISION, F_FILE
from .documents.docx_writer import write_docx
from .documents.loaders import InputDoc, _docx_lines, discover_inputs, iter_work_batches
from .llm.base import DocumentAI, PIIEntity
from .llm.factory import get_provider
from .utils.logging import get_logger

log = get_logger()


@dataclass
class RunOptions:
    limit: Optional[int] = None
    overwrite: bool = False     # reprocess even if output exists / state says done
    resume: bool = True         # skip documents already marked done


@dataclass
class LinkPayload:
    """Case-linkage data returned by a worker for main-thread SQLite ingest."""
    doc_id: str
    source: str
    level: str
    own: Ident
    category: str
    outcome: str
    refs: List[Ident]


@dataclass
class DocExtra:
    """Everything the JSON/XLSX record needs that isn't in DocRecord or the casedb."""
    source_file: str
    fmt: str
    read_method: str
    calls: int
    fields: dict                 # {label: {value, confidence, source}}
    pii_types: List[str]
    leak_passed: bool
    leak_hits: int
    leaked: List[str]
    quarantined: bool
    quarantine_reason: str
    verify_found: List[str]
    category_source: str        # detected | assumed-from-folder | undetermined


def _field_meta(llm_val: str, loc_val: str) -> dict:
    """Reconcile the LLM value and the deterministic (regex) value into one field."""
    llm_val, loc_val = (llm_val or "").strip(), (loc_val or "").strip()
    if llm_val and loc_val and llm_val == loc_val:
        return {"value": llm_val, "confidence": 0.97, "source": "llm+regex"}
    if llm_val:
        return {"value": llm_val, "confidence": 0.9, "source": "llm"}
    if loc_val:
        return {"value": loc_val, "confidence": 0.8, "source": "regex"}
    return {"value": "", "confidence": 0.0, "source": "none"}


class Pipeline:
    def __init__(self, settings: Settings, provider: Optional[DocumentAI] = None):
        self.settings = settings
        self.provider = provider or get_provider(settings)
        self.state = State(settings.state_file)
        # SQLite is used only from the main thread (workers return LinkPayloads).
        self.casedb = CaseDB(settings.db_path)

    def _output_path(self, doc: InputDoc) -> Path:
        return self.settings.output_dir / (doc.doc_id + ".docx")

    def _process_one(self, doc: InputDoc) -> tuple[DocRecord, LinkPayload]:
        """Process a single document end to end. Runs in a worker thread."""
        all_pages: List[str] = []
        in_tok = out_tok = cached_tok = 0
        # A batch's PII list applies to the whole batch, but any single value
        # lives on just one page. So track matches at the document level and
        # only report a value as unmatched if it was found on NO page anywhere.
        flagged_values: set[str] = set()
        matched_values: set[str] = set()
        pii_types: set[str] = set()
        struct_hits = 0
        calls = 0
        saw_image = False
        category = court = ""
        identity = None
        refs = []
        raw_pages: List[str] = []   # un-redacted text, for local identifier extraction

        for batch in iter_work_batches(doc, self.settings.pages_per_batch,
                                       soffice_path=self.settings.soffice_path):
            if batch.kind == "image":
                result = self.provider.process_pdf(batch.pdf_bytes, batch.page_count)
                pages = _align_pages(result.pages, batch.page_count)  # OCR text
                saw_image = True
            else:  # "text": we already have the text locally
                result = self.provider.process_text("\n".join(batch.pages))
                pages = batch.pages

            calls += 1
            in_tok += result.input_tokens
            out_tok += result.output_tokens
            cached_tok += result.cached_tokens
            flagged_values.update(e.text for e in result.pii if e.text.strip())
            pii_types.update(
                (getattr(e, "type", "") or getattr(e, "label", "") or "").strip()
                for e in result.pii
            )
            # Classification comes from the header pages; take the first batch
            # that produced a usable value.
            if not category and result.category:
                category = normalize_category(result.category)
            if not court and result.court:
                court = result.court
            # Case identity from the first batch that carries one; collect all refs.
            if identity is None and result.identity and (
                result.identity.level or result.identity.file_no or result.identity.decision_no
            ):
                identity = result.identity
            refs.extend(result.refs)

            for page_text in pages:
                raw_pages.append(page_text)
                clean, report = redact_text(
                    page_text, result.pii, self.settings.replacement_token
                )
                # deterministic backstop: strip structured PII the model may have missed
                clean, n_struct = redact_structured(clean, self.settings.replacement_token)
                struct_hits += n_struct
                all_pages.append(clean)
                matched_values.update(report.replaced)

        unmatched_values = sorted(flagged_values - matched_values)
        for value in unmatched_values:
            log.warning("[%s] PII flagged but not found in text: %r", doc.doc_id, value)

        # Verification pass (opt-in, ADVISORY): an independent re-read surfaces anything
        # that *might* be a missed name, for a human to review in the platform. It is NOT
        # acted on automatically — on real rulings it flags institutions/roles (the State,
        # endowment administrators) as often as people, so auto-redacting or auto-
        # quarantining on it would degrade correctly-anonymized documents.
        verify_found: List[str] = []
        if self.settings.verify_pass and any(p.strip() for p in all_pages):
            remaining, vi, vo = self.provider.verify_pii(
                "\n".join(all_pages), self.settings.replacement_token)
            in_tok += vi
            out_tok += vo
            if remaining:
                verify_found = remaining
                log.info("[VERIFY] %s: %d item(s) flagged for human review: %s",
                         doc.doc_id, len(remaining), ", ".join(remaining[:5]))

        # Operator fallback: if the model couldn't classify, use the folder-level
        # chamber the operator supplied. Never overrides a confident model answer.
        # The source is recorded so an assumed chamber can always be told apart from a
        # detected one — the folder is not 100% one chamber, so assumptions need review.
        cat_source = "detected" if (category and category != UNKNOWN) else "undetermined"
        if (not category or category == UNKNOWN) and self.settings.default_category:
            category = normalize_category(self.settings.default_category)
            cat_source = "assumed-from-folder"

        # Title for the document = "court — chamber" (skip unknown/empty parts).
        title_parts = [p for p in (court, category) if p and p != UNKNOWN]
        title = " — ".join(title_parts) if title_parts else doc.doc_id

        out_path = self._output_path(doc)
        write_docx(all_pages, out_path, title=title)

        # Release gate: re-scan the DELIVERED file for any known PII. Zero hits, or
        # the file is quarantined (moved out of the clean output dir) so a leaking
        # artifact is never delivered. A re-run reprocesses it (output absent).
        delivered = "\n".join(_docx_lines(out_path))
        leak = leak_scan(delivered, sorted(flagged_values))
        garbled = _ocr_garbled(delivered)
        quarantined = (not leak.passed) or garbled
        q_reason = "leak" if not leak.passed else ("poor-ocr" if garbled else "")
        if quarantined:
            qdir = self.settings.output_dir / "_quarantine"
            qdir.mkdir(parents=True, exist_ok=True)
            qpath = qdir / out_path.name
            out_path.replace(qpath)
            out_path = qpath
            if not leak.passed:
                log.error("[LEAK] %s: %d hit(s) survived redaction: %s",
                          doc.doc_id, leak.hits, ", ".join(leak.leaked[:5]))
            else:
                log.error("[POOR-OCR] %s: garbled scan — quarantined for manual review",
                          doc.doc_id)

        cost = self.settings.estimate_cost(in_tok, out_tok, cached_tok)
        record = DocRecord(
            status="done",           # processed; leak status is tracked separately
            output=str(out_path),
            category=category or UNKNOWN,
            court=court,
            pages=len(all_pages),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
            pii_count=len(matched_values) + struct_hits,
            unmatched=len(unmatched_values),
            ts=_dt.datetime.now().isoformat(timespec="seconds"),
        )
        # Deterministic local extraction as a backstop for LLM inconsistency,
        # then merge: prefer the LLM's value, fall back to the local one per field.
        loc_level, loc_own, loc_refs = local_extract("\n".join(raw_pages))

        def pick(llm_val: str, loc_val: str) -> str:
            return llm_val if (llm_val and llm_val.strip()) else loc_val

        level = pick(identity.level if identity else "", loc_level)
        own = Ident(
            court=pick(identity.court if identity else (court or ""), loc_own.court),
            city=pick(identity.city if identity else "", loc_own.city),
            decision_no=pick(identity.decision_no if identity else "", loc_own.decision_no),
            date=pick(identity.date if identity else "", loc_own.date),
            file_no=pick(identity.file_no if identity else "", loc_own.file_no),
        )
        # Combine LLM refs + local refs, dedup by file/decision.
        merged_refs: list[Ident] = []
        seen: set[str] = set()
        llm_refs = [Ident(r.court, r.city, r.decision_no, r.date, r.file_no) for r in refs]
        for r in llm_refs + loc_refs:
            key = r.file_norm or r.decision_no
            if not key or key in seen:
                continue
            seen.add(key)
            merged_refs.append(r)

        payload = LinkPayload(
            doc_id=doc.doc_id,
            source=str(doc.path),
            level=level,
            own=own,
            category=category or UNKNOWN,
            outcome=(identity.outcome if identity else ""),
            refs=merged_refs,
        )
        fields = {
            F_DECISION: _field_meta(identity.decision_no if identity else "", loc_own.decision_no),
            F_FILE: _field_meta(identity.file_no if identity else "", loc_own.file_no),
            F_DATE: _field_meta(identity.date if identity else "", loc_own.date),
        }
        extra = DocExtra(
            source_file=doc.path.name,
            fmt=doc.path.suffix.lower().lstrip("."),
            read_method="vision-ocr" if saw_image else "text",
            calls=calls,
            fields=fields,
            pii_types=sorted(t for t in pii_types if t),
            leak_passed=leak.passed,
            leak_hits=leak.hits,
            leaked=leak.leaked,
            quarantined=quarantined,
            quarantine_reason=q_reason,
            verify_found=verify_found,
            category_source=cat_source,
        )
        return record, payload, extra

    def _should_skip(self, doc: InputDoc, opts: RunOptions) -> bool:
        if opts.overwrite:
            return False
        if opts.resume and self.state.is_done(doc.doc_id) and self._output_path(doc).exists():
            return True
        return False

    def run(self, opts: RunOptions, progress_cb: Optional[Callable[[dict], None]] = None) -> dict:
        docs = discover_inputs(self.settings.input_dir)
        if not docs:
            log.warning("No .pdf or .docx files found under %s", self.settings.input_dir)
            return self.state.totals()

        todo = [d for d in docs if not self._should_skip(d, opts)]
        skipped = len(docs) - len(todo)
        if opts.limit is not None:
            todo = todo[: opts.limit]

        log.info(
            "Found %d PDF(s): %d to process, %d skipped (already done).",
            len(docs), len(todo), skipped,
        )

        if not todo:
            return self.state.totals()

        total = len(todo)
        done = 0
        extras: dict[str, DocExtra] = {}
        failed_docs: List[dict] = []
        cumulative_cost = 0.0
        n_quarantined = 0
        halted = False
        budget = self.settings.budget_usd
        bar = None
        with logging_redirect_tqdm(), ThreadPoolExecutor(max_workers=self.settings.max_workers) as pool:
            futures = {pool.submit(self._process_one, d): d for d in todo}
            bar = tqdm(as_completed(futures), total=len(futures), desc="Anonymizing",
                       unit="doc", smoothing=0.1)
            for fut in bar:
                doc = futures[fut]
                event = {"done": 0, "total": total, "doc_id": doc.doc_id, "ok": True}
                try:
                    record, payload, extra = fut.result()
                    self.state.update(doc.doc_id, record)
                    extras[doc.doc_id] = extra
                    cumulative_cost += record.cost
                    if extra.quarantined:
                        n_quarantined += 1
                    # Ingest case-linkage data (main thread only — SQLite).
                    self.casedb.ingest(
                        doc_id=payload.doc_id, source=payload.source, level=payload.level,
                        own=payload.own, category=payload.category,
                        outcome=payload.outcome, refs=payload.refs,
                        pii_count=record.pii_count,
                    )
                    log.info(
                        "[%s] %s -> %s | %s | %s | %d pages | %d PII | $%.4f%s%s",
                        extra.quarantine_reason.upper() if extra.quarantined else "OK",
                        doc.doc_id, record.output, record.category or UNKNOWN,
                        payload.level or "?",
                        record.pages, record.pii_count, record.cost,
                        f" | {record.unmatched} unmatched" if record.unmatched else "",
                        f" | QUARANTINED ({extra.quarantine_reason})" if extra.quarantined else "",
                    )
                    event.update(category=record.category, level=payload.level or "?",
                                 pii=record.pii_count, cost=record.cost)
                except Exception as exc:  # isolate per-document failures
                    log.exception("[FAIL] %s: %s", doc.doc_id, exc)
                    self.state.update(
                        doc.doc_id,
                        DocRecord(
                            status="failed",
                            error=str(exc),
                            ts=_dt.datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    failed_docs.append({"doc_id": doc.doc_id, "source_file": doc.path.name,
                                        "reason": "error", "detail": str(exc)})
                    event.update(ok=False, error=str(exc))
                done += 1
                event["done"] = done
                if bar is not None:
                    bar.set_postfix_str(
                        f"${cumulative_cost:.3f} | clean {done - len(failed_docs) - n_quarantined}"
                        f" | held {n_quarantined} | fail {len(failed_docs)}")
                if progress_cb:
                    try:
                        progress_cb(event)
                    except Exception:  # UI callback must never break the run
                        pass
                # Hard budget ceiling (Script.md §3.3): stop as soon as it is reached.
                if budget and cumulative_cost >= budget:
                    halted = True
                    log.error("[BUDGET] ceiling $%.2f reached ($%.4f spent) — halting run.",
                              budget, cumulative_cost)
                    for pending in futures:
                        pending.cancel()
                    break

        # Side mission: write the file -> category index for every done document.
        index_path = self.settings.output_dir / "index.csv"
        n = self.state.export_index(index_path)
        log.info("Wrote category index: %s (%d documents)", index_path, n)

        # Case linkage: rebuild edges across all stored docs and export cases.csv.
        self.casedb.relink()
        cases_path = self.settings.output_dir / "cases.csv"
        c = self.casedb.export_cases_csv(cases_path)
        self.casedb.export_documents_csv(self.settings.output_dir / "documents.csv")
        log.info("Linked cases -> %s (%d cases)", cases_path, c)

        # Structured hand-off (Script.md §7): JSON + XLSX records, run report, quarantine.
        out = self.settings.output_dir
        records_list: List[dict] = []
        quarantined: List[dict] = list(failed_docs)
        for doc_id, extra in sorted(extras.items()):
            st = self.state.get(doc_id)
            if st is None:
                continue
            cdoc = self.casedb.document(doc_id)
            records_list.append({
                "doc_id": doc_id,
                "source_file": extra.source_file,
                "format": extra.fmt,
                "read_method": extra.read_method,
                "fields": extra.fields,
                "category": {"value": cdoc.get("category") or st.category or UNKNOWN,
                             "source": extra.category_source},
                "level": cdoc.get("level") or "",
                "case_id": cdoc.get("case_id") or "",
                "review": "check" if extra.verify_found else (cdoc.get("review") or "ok"),
                "review_notes": extra.verify_found,
                "links": self.casedb.links_for(doc_id),
                "pii": {"removed_count": st.pii_count, "types": extra.pii_types},
                "anonymized_file": Path(st.output).name,
                "quarantined": extra.quarantined,
                "leak_test": {"passed": extra.leak_passed, "hits": extra.leak_hits,
                              "leaked_count": len(extra.leaked)},
                "cost": {"calls": extra.calls, "input_tokens": st.input_tokens,
                         "output_tokens": st.output_tokens, "usd": round(st.cost, 6)},
                "pages": st.pages,
                "status": "quarantined" if extra.quarantined else "done",
                "audit": {"model": self.settings.model, "timestamp": st.ts},
            })
            if extra.quarantined:
                detail = (f"{extra.leak_hits} hit(s): " + ", ".join(extra.leaked[:3])
                          if extra.quarantine_reason == "leak" else "garbled OCR — manual review")
                quarantined.append({
                    "doc_id": doc_id, "source_file": extra.source_file,
                    "reason": extra.quarantine_reason, "detail": detail,
                })

        records_mod.write_json(records_list, out / "records.json")
        records_mod.write_xlsx(records_list, out / "records.xlsx")
        records_mod.write_quarantine_csv(quarantined, out / "quarantine.csv")
        totals = self.state.totals()
        records_mod.write_run_report(
            totals, records_list, quarantined,
            model=self.settings.model, budget_usd=self.settings.budget_usd,
            path_md=out / "run_report.md", path_json=out / "run_report.json",
            halted=halted,
        )
        log.info("Wrote records.json / records.xlsx / run_report.md (%d docs, %d quarantined)",
                 len(records_list), len(quarantined))

        totals["quarantined"] = len(quarantined)
        totals["leaked"] = sum(1 for r in records_list if not r["leak_test"]["passed"])
        totals["halted"] = halted
        return totals


def _ocr_garbled(text: str) -> bool:
    """True if the scan came back unreadable (see core.quality)."""
    return ocr_garbled(text)


def _align_pages(pages: List[str], expected: int) -> List[str]:
    """Make the OCR page list length match the batch's actual page count."""
    if len(pages) == expected:
        return pages
    if len(pages) < expected:
        return pages + [""] * (expected - len(pages))
    return pages[:expected]
