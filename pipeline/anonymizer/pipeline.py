"""Orchestration: discover PDFs -> OCR+PII per batch -> redact -> write .docx.

Documents are processed concurrently (API calls are I/O-bound). Each document is
isolated: one failure is logged and skipped, the run continues. Progress and the
resume checkpoint are updated after every document.
"""
from __future__ import annotations

import datetime as _dt
import json
import random
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .config import Settings
from .core.casedb import CaseDB
from .core.categories import UNKNOWN, normalize_category
from .core.dedupe import HashCache, split_duplicates
from .core.fields import (chamber_from_text, display_date, display_decision_no,
                          header_date, origin_city)
from .core.identifiers import Ident, local_extract, split_file_numbers
from .core.leaktest import leak_scan
from .core.quality import ocr_garbled
from .core.redactor import redact_structured, redact_text
from .core.state import DocRecord, State
from .documents import records as records_mod
from .documents.records import F_CHAMBER, F_CITY, F_DATE, F_DECISION, F_FILE
from .documents.docx_writer import retitle_docx, write_docx
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
    sample: Optional[int] = None  # process a random N (fixed seed) instead of the first N


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
    listing: dict        # display fields for the case DB (see CaseDB.LISTING_KEYS)


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
    category_source: str        # ruling-text | model | assumed-from-folder | undetermined
    origin_city: str = ""
    origin_city_source: str = ""


def _field_meta(llm_val: str, loc_val: str, show: Callable[[str], str] = str.strip) -> dict:
    """Reconcile the LLM value and the deterministic (regex) value into one field.

    `show` turns a raw value into the form a listing displays ("33/1" -> "33");
    agreement is judged on that form, and the raw text is kept alongside.
    """
    llm_raw, loc_raw = (llm_val or "").strip(), (loc_val or "").strip()
    llm_v, loc_v = show(llm_raw), show(loc_raw)
    if llm_v and loc_v and llm_v == loc_v:
        return {"value": llm_v, "raw": llm_raw, "confidence": 0.97, "source": "llm+regex"}
    if llm_v:
        return {"value": llm_v, "raw": llm_raw, "confidence": 0.9, "source": "llm"}
    if loc_v:
        return {"value": loc_v, "raw": loc_raw, "confidence": 0.8, "source": "regex"}
    return {"value": "", "raw": llm_raw or loc_raw, "confidence": 0.0, "source": "none"}


# An output with less visible text than this is not a ruling, whatever the leak
# gate says: 63 delivered files held nothing but their title after the model read
# a scan back as blank pages -- and an empty file has no names left to find.
EMPTY_MIN_CHARS = 200
EMPTY_MIN_CHARS_PER_PAGE = 60
# A multi-page ruling averaging less than this per page stopped transcribing early.
# Across 3,174 delivered rulings the lowest real ones held ~670 per page; the five
# partial ones held 61-336. Only the conclusion of the ruling had come back.
PARTIAL_MAX_CHARS_PER_PAGE = 400


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

        # Chamber, most reliable source first. What the ruling states about itself
        # ("في الملف الشرعي رقم ...") names the chamber that issued it; the model
        # classifies by topic instead, and read child-support rulings as "social" --
        # 234 personal-status rulings mislabelled in one folder. Then the model, then
        # the operator's folder-level hint. The source is always recorded.
        raw_text = "\n".join(raw_pages)
        stated = chamber_from_text(raw_text)
        if stated:
            category, cat_source = stated, "ruling-text"
        elif category and category != UNKNOWN:
            cat_source = "model"
        elif self.settings.default_category:
            category = normalize_category(self.settings.default_category)
            cat_source = "assumed-from-folder"
        else:
            category, cat_source = UNKNOWN, "undetermined"

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
        visible = len(re.sub(r"\s", "", delivered)) - len(re.sub(r"\s", "", title))
        empty = visible < max(EMPTY_MIN_CHARS, EMPTY_MIN_CHARS_PER_PAGE * len(all_pages))
        partial = (not empty and len(all_pages) > 1
                   and visible / len(all_pages) < PARTIAL_MAX_CHARS_PER_PAGE)
        quarantined = (not leak.passed) or garbled or empty or partial
        q_reason = ("leak" if not leak.passed else "poor-ocr" if garbled
                    else "empty" if empty else "partial" if partial else "")
        if quarantined:
            qdir = self.settings.output_dir / "_quarantine"
            qdir.mkdir(parents=True, exist_ok=True)
            qpath = qdir / out_path.name
            out_path.replace(qpath)
            out_path = qpath
            if not leak.passed:
                log.error("[LEAK] %s: %d hit(s) survived redaction: %s",
                          doc.doc_id, leak.hits, ", ".join(leak.leaked[:5]))
            elif garbled:
                log.error("[POOR-OCR] %s: garbled scan — quarantined for manual review",
                          doc.doc_id)
            else:
                log.error("[%s] %s: only %d characters of text for %d page(s) — held, "
                          "not delivered; a rerun retries it", q_reason.upper(), doc.doc_id,
                          visible, len(all_pages))
        else:
            # This document was held by an earlier run and has now passed. Drop that
            # copy: it is the version that still contained the PII, and leaving it
            # behind both keeps a leaking artifact on disk and overstates how many
            # files actually need review.
            stale = self.settings.output_dir / "_quarantine" / out_path.name
            if stale.exists():
                stale.unlink()
                log.info("[CLEARED] %s: passed on re-run; removed stale quarantine copy",
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
        loc_level, loc_own, loc_refs = local_extract(raw_text)

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
        # The model reports several joined files in one field when a ruling reviews
        # more than one ("444/1606/2016 وعدد445/1606/2016"). Left whole, canon_file_no
        # runs the digits together into a key that matches nothing, so the lower
        # rulings are never linked. Split it the same way the local extractor does.
        llm_refs = [
            Ident(r.court, r.city, r.decision_no, r.date, file_no)
            for r in refs
            for file_no in split_file_numbers(r.file_no)
        ]
        for r in llm_refs + loc_refs:
            key = r.file_norm or r.decision_no
            if not key or key in seen:
                continue
            seen.add(key)
            merged_refs.append(r)

        fields = {
            F_DECISION: _field_meta(identity.decision_no if identity else "",
                                    loc_own.decision_no, display_decision_no),
            F_FILE: _field_meta(identity.file_no if identity else "", loc_own.file_no),
            F_DATE: _field_meta(identity.date if identity else "", loc_own.date, display_date),
        }
        if not fields[F_DATE]["value"]:
            stated_date = header_date(raw_text)
            if stated_date:
                fields[F_DATE].update(value=stated_date, confidence=0.8, source="header")
        # The ruling's own city is always Rabat; a listing shows the lower court's.
        city, city_source = origin_city(merged_refs, raw_text)
        fields[F_CITY] = {"value": city, "confidence": 0.9 if city_source == "appeal" else
                          0.8 if city else 0.0, "source": city_source or "none"}
        fields[F_CHAMBER] = {"value": category or UNKNOWN, "source": cat_source,
                             "confidence": 0.97 if cat_source == "ruling-text" else
                             0.8 if cat_source == "model" else 0.5}

        payload = LinkPayload(
            doc_id=doc.doc_id,
            source=str(doc.path),
            level=level,
            own=own,
            category=category or UNKNOWN,
            outcome=(identity.outcome if identity else ""),
            refs=merged_refs,
            listing={"decision_display": fields[F_DECISION]["value"],
                     "date_display": fields[F_DATE]["value"],
                     "origin_city": city, "origin_city_source": city_source,
                     "category_source": cat_source},
        )
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
            origin_city=city,
            origin_city_source=city_source,
        )
        return record, payload, extra

    def _should_skip(self, doc: InputDoc, opts: RunOptions) -> bool:
        if opts.overwrite:
            return False
        if opts.resume and self.state.is_done(doc.doc_id) and self._output_path(doc).exists():
            return True
        return False

    # --- duplicates ---------------------------------------------------------
    def _drop_duplicates(self, docs: List[InputDoc]) -> List[InputDoc]:
        """Keep one document per distinct file content; retire the copies.

        A copy already processed by an earlier run (before copies were detected)
        is retired too: its output moves to _duplicates/ and its database row goes,
        so it is neither listed nor counted twice. What was spent on it stays in
        the cost totals.
        """
        cache = HashCache(self.settings.output_dir / ".hashes.json")
        self._hashes = {}
        for d in tqdm(docs, desc="Fingerprinting", unit="file", leave=False):
            self._hashes[d.doc_id] = cache.get(d.path)
        cache.save()

        keep, copies = split_duplicates(docs, self._hashes, self.casedb.known_hashes(),
                                        self.state.is_done)
        for copy_id, original in copies.items():
            self._retire_copy(copy_id, original)

        # Rulings already in the database from an earlier run carry no fingerprint
        # or folder label yet; stamp them so later folders can find their copies.
        corpus = self.settings.corpus_label
        for d in keep:
            row = self.casedb.document(d.doc_id)
            if row and (row.get("content_hash") != self._hashes[d.doc_id]
                        or row.get("corpus") != corpus):
                self.casedb.update_listing(d.doc_id, content_hash=self._hashes[d.doc_id],
                                           corpus=corpus)
        return keep

    def _retire_copy(self, copy_id: str, original: str) -> None:
        out = self.settings.output_dir
        for where in (out, out / "_quarantine"):
            f = where / (copy_id + ".docx")
            if f.exists():
                dest = out / "_duplicates" / f.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dest))
        sidecar = self._sidecar(copy_id)
        if sidecar.exists():
            sidecar.unlink()
        if self.casedb.document(copy_id):
            self.casedb.remove(copy_id)
        rec = self.state.get(copy_id)
        if rec is None or rec.status != "duplicate":
            self.state.mark_duplicate(copy_id, original)

    # --- per-document records -------------------------------------------------
    def _sidecar(self, doc_id: str) -> Path:
        return self.settings.output_dir / "_records" / (doc_id + ".json")

    def _save_record(self, doc_id: str, record: DocRecord, extra: DocExtra) -> None:
        """Persist this document's record the moment it is processed.

        records.json used to be assembled from memory at the very end of a run, so a
        run that was stopped, or resumed, lost every earlier record: after four
        resumed runs over 3,239 rulings it described 11. Each record now lives in
        _records/ and records.json is rebuilt from all of them. No personal data is
        written here -- leak hits are counted, never quoted.
        """
        if extra.quarantine_reason == "leak":
            detail = f"{extra.leak_hits} surviving name(s) — open the held file to review"
        elif extra.quarantine_reason == "poor-ocr":
            detail = "garbled OCR — manual review"
        elif extra.quarantine_reason == "empty":
            detail = "almost no text came back — a rerun retries it"
        elif extra.quarantine_reason == "partial":
            detail = "transcription stopped early — a rerun retries it"
        else:
            detail = ""
        data = {
            "doc_id": doc_id,
            "source_file": extra.source_file,
            "format": extra.fmt,
            "read_method": extra.read_method,
            "fields": extra.fields,
            "category": {"value": record.category or UNKNOWN, "source": extra.category_source},
            "review_notes": extra.verify_found,
            "pii": {"removed_count": record.pii_count, "types": extra.pii_types},
            "anonymized_file": Path(record.output).name,
            "quarantined": extra.quarantined,
            "quarantine_reason": extra.quarantine_reason,
            "quarantine_detail": detail,
            "leak_test": {"passed": extra.leak_passed, "hits": extra.leak_hits,
                          "leaked_count": len(extra.leaked)},
            "cost": {"calls": extra.calls, "input_tokens": record.input_tokens,
                     "output_tokens": record.output_tokens, "usd": round(record.cost, 6)},
            "pages": record.pages,
            "audit": {"model": self.settings.model, "timestamp": record.ts},
        }
        path = self._sidecar(doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def _legacy_record(self, doc_id: str, st: DocRecord, cdoc: dict) -> dict:
        """A record for a document processed before records were kept per document.

        Rebuilt from the state file and the case database; what was never stored
        (read method, PII types, the leak detail) is left empty rather than guessed.
        """
        held = "_quarantine" in (st.output or "")
        return {
            "doc_id": doc_id,
            "source_file": Path(cdoc.get("source") or doc_id).name,
            "format": Path(cdoc.get("source") or "").suffix.lstrip("."),
            "read_method": "",
            "fields": {},
            "category": {"value": cdoc.get("category") or st.category or UNKNOWN,
                         "source": cdoc.get("category_source") or ""},
            "review_notes": [],
            "pii": {"removed_count": st.pii_count, "types": []},
            "anonymized_file": Path(st.output).name,
            "quarantined": held,
            "quarantine_reason": "held" if held else "",
            "quarantine_detail": "held by an earlier run — open the file to review" if held else "",
            "leak_test": {"passed": (None if held else True), "hits": 0, "leaked_count": 0},
            "cost": {"calls": 0, "input_tokens": st.input_tokens,
                     "output_tokens": st.output_tokens, "usd": round(st.cost, 6)},
            "pages": st.pages,
            "audit": {"model": self.settings.model, "timestamp": st.ts},
        }

    # --- run ----------------------------------------------------------------
    def run(self, opts: RunOptions, progress_cb: Optional[Callable[[dict], None]] = None) -> dict:
        docs = discover_inputs(self.settings.input_dir)
        if not docs:
            log.warning("No .pdf or .docx files found under %s", self.settings.input_dir)
            return self.state.totals()

        found = len(docs)
        docs = self._drop_duplicates(docs)
        todo = [d for d in docs if not self._should_skip(d, opts)]
        skipped = len(docs) - len(todo)
        if opts.sample is not None:
            # The first N in name order is not a fair test: in one folder they were
            # nearly all 1970s rulings with numeric names. A seeded draw is
            # representative and repeatable.
            todo = sorted(random.Random(0).sample(todo, min(opts.sample, len(todo))),
                          key=lambda d: d.doc_id)
        if opts.limit is not None:
            todo = todo[: opts.limit]

        log.info(
            "Found %d file(s): %d distinct rulings (%d duplicate copies skipped) — "
            "%d to process, %d already done.",
            found, len(docs), found - len(docs), len(todo), skipped,
        )

        halted = self._process_all(todo, progress_cb) if todo else False
        return self.export(halted)

    def _process_all(self, todo: List[InputDoc],
                     progress_cb: Optional[Callable[[dict], None]]) -> bool:
        """Process `todo` concurrently. Returns True if the budget ceiling halted it."""
        total = len(todo)
        done = n_failed = n_quarantined = 0
        cumulative_cost = 0.0
        halted = False
        budget = self.settings.budget_usd
        corpus = self.settings.corpus_label
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
                    self._save_record(doc.doc_id, record, extra)
                    cumulative_cost += record.cost
                    if extra.quarantined:
                        n_quarantined += 1
                    # Ingest case-linkage data (main thread only — SQLite).
                    self.casedb.ingest(
                        doc_id=payload.doc_id, source=payload.source, level=payload.level,
                        own=payload.own, category=payload.category,
                        outcome=payload.outcome, refs=payload.refs,
                        pii_count=record.pii_count,
                        listing={**payload.listing, "corpus": corpus,
                                 "content_hash": self._hashes.get(doc.doc_id, "")},
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
                    n_failed += 1
                    self.state.update(
                        doc.doc_id,
                        DocRecord(
                            status="failed",
                            error=str(exc),
                            ts=_dt.datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    event.update(ok=False, error=str(exc))
                done += 1
                event["done"] = done
                bar.set_postfix_str(
                    f"${cumulative_cost:.3f} | clean {done - n_failed - n_quarantined}"
                    f" | held {n_quarantined} | fail {n_failed}")
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
        return halted

    def export(self, halted: bool = False) -> dict:
        """Write every export for this folder, covering all its documents, not one run."""
        out = self.settings.output_dir
        corpus = self.settings.corpus_label

        # Side mission: the file -> category index for every done document.
        n = self.state.export_index(out / "index.csv")
        log.info("Wrote category index: %s (%d documents)", out / "index.csv", n)

        # Case linkage across everything in the database; exports keep to this folder.
        self.casedb.relink()
        c = self.casedb.export_cases_csv(out / "cases.csv", corpus=corpus)
        self.casedb.export_documents_csv(out / "documents.csv", corpus=corpus)
        # The listing is what a reader browses: only rulings actually delivered.
        delivered = {d for d, st in self.state.items()
                     if st.status == "done" and "_quarantine" not in (st.output or "")}
        listed = self.casedb.export_listing_csv(out / "listing.csv", corpus=corpus,
                                                only=delivered)
        log.info("Linked cases -> %s (%d cases); listing.csv (%d rulings)",
                 out / "cases.csv", c, listed)

        records_list: List[dict] = []
        quarantined: List[dict] = []
        duplicates: List[dict] = []
        for doc_id, st in sorted(self.state.items()):
            if st.status == "duplicate":
                duplicates.append({"file": doc_id, "same_as": st.error.replace("copy of ", "")})
                continue
            if st.status == "failed":
                quarantined.append({"doc_id": doc_id, "source_file": "",
                                    "reason": "error", "detail": st.error})
                continue
            cdoc = self.casedb.document(doc_id)
            sidecar = self._sidecar(doc_id)
            if sidecar.exists():
                rec = json.loads(sidecar.read_text(encoding="utf-8"))
            else:
                rec = self._legacy_record(doc_id, st, cdoc)
            # Values that change as other rulings arrive come from the database now.
            rec["category"]["value"] = cdoc.get("category") or rec["category"]["value"]
            if cdoc.get("category_source"):
                rec["category"]["source"] = cdoc["category_source"]
            rec["level"] = cdoc.get("level") or ""
            rec["case_id"] = cdoc.get("case_id") or ""
            rec["review"] = "check" if rec.get("review_notes") else (cdoc.get("review") or "ok")
            rec["links"] = self.casedb.links_for(doc_id)
            rec["city"] = cdoc.get("origin_city") or ""
            date = cdoc.get("date_display") or ""
            rec["year"] = date[-4:] if date else ""
            rec["status"] = "quarantined" if rec.get("quarantined") else "done"
            records_list.append(rec)
            if rec.get("quarantined"):
                quarantined.append({"doc_id": doc_id, "source_file": rec.get("source_file", ""),
                                    "reason": rec.get("quarantine_reason", ""),
                                    "detail": rec.get("quarantine_detail", "")})

        records_mod.write_json(records_list, out / "records.json")
        records_mod.write_xlsx(records_list, out / "records.xlsx")
        records_mod.write_quarantine_csv(quarantined, out / "quarantine.csv")
        records_mod.write_duplicates_csv(duplicates, out / "duplicates.csv")
        totals = self.state.totals()
        records_mod.write_run_report(
            totals, records_list, quarantined,
            model=self.settings.model, budget_usd=self.settings.budget_usd,
            path_md=out / "run_report.md", path_json=out / "run_report.json",
            halted=halted,
        )
        log.info("Wrote records.json / records.xlsx / run_report.md (%d docs, %d held or "
                 "failed, %d duplicate copies)", len(records_list), len(quarantined),
                 len(duplicates))

        totals["quarantined"] = len(quarantined)
        totals["leaked"] = sum(1 for r in records_list if r.get("quarantine_reason") == "leak")
        totals["halted"] = halted
        return totals


    # --- maintenance: repair past output without reprocessing ------------------
    def _delivered_path(self, doc_id: str) -> Optional[Path]:
        out = self.settings.output_dir
        for where in (out, out / "_quarantine"):
            f = where / (doc_id + ".docx")
            if f.exists():
                return f
        return None

    def refresh_listing(self) -> dict:
        """Recompute the listing fields of already-processed rulings. No model calls.

        Reads what the pipeline stored -- the case database and the delivered text --
        and applies the current rules for decision number, date, chamber and the
        lower court's city. When the chamber changes, the title line of the delivered
        file is corrected too.
        """
        counts = {"rulings": 0, "chamber_changed": 0, "retitled": 0}
        for doc_id, st in self.state.items():
            if st.status != "done":
                continue
            path = self._delivered_path(doc_id)
            if path is None:
                continue
            lines = _docx_lines(path)
            text = "\n".join(lines[1:])          # line 0 is our own title
            cdoc = self.casedb.document(doc_id)
            if not cdoc:
                # Processed before the case database lived beside this output: rebuild
                # its row from the delivered text so it is not missing from listings.
                level, own, refs = local_extract(text)
                self.casedb.ingest(doc_id, source="", level=level, own=own,
                                   category=st.category or UNKNOWN, outcome="", refs=refs,
                                   pii_count=st.pii_count,
                                   listing={"corpus": self.settings.corpus_label})
                cdoc = self.casedb.document(doc_id)
                counts["rows_rebuilt"] = counts.get("rows_rebuilt", 0) + 1
            counts["rulings"] += 1

            stated = chamber_from_text(text)
            old_cat = cdoc.get("category") or ""
            if stated:
                category, source = stated, "ruling-text"
            elif cdoc.get("category_source"):
                category, source = old_cat, cdoc["category_source"]
            elif old_cat and old_cat != UNKNOWN:
                category, source = old_cat, "model"
            else:
                category, source = UNKNOWN, "undetermined"

            _, loc_own, _ = local_extract(text)
            decision = (display_decision_no(cdoc.get("decision_no") or "")
                        or display_decision_no(loc_own.decision_no))
            date = (display_date(cdoc.get("date") or "") or header_date(text)
                    or display_date(loc_own.date))
            city, city_source = origin_city(self.casedb.refs_for(doc_id), text)

            self.casedb.update_listing(
                doc_id, category=category, category_source=source,
                decision_display=decision, date_display=date,
                origin_city=city, origin_city_source=city_source,
                corpus=self.settings.corpus_label)
            if category != old_cat:
                counts["chamber_changed"] += 1
                st.category = category
                self.state.update(doc_id, st)
                court = cdoc.get("court") or ""
                title = " — ".join(p for p in (court, category) if p and p != UNKNOWN)
                if title and retitle_docx(path, title):
                    counts["retitled"] += 1
            sidecar = self._sidecar(doc_id)
            if sidecar.exists():
                rec = json.loads(sidecar.read_text(encoding="utf-8"))
                rec["category"] = {"value": category, "source": source}
                fields = rec.setdefault("fields", {})
                fields.setdefault(F_DECISION, {})["value"] = decision
                fields.setdefault(F_DATE, {})["value"] = date
                fields[F_CITY] = {"value": city, "source": city_source or "none"}
                fields[F_CHAMBER] = {"value": category, "source": source}
                sidecar.write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        log.info("Refreshed listing fields for %d rulings (%d chamber corrections, "
                 "%d titles rewritten)", counts["rulings"], counts["chamber_changed"],
                 counts["retitled"])
        return counts

    def requeue_damaged(self) -> dict:
        """Set aside delivered files that are not fit to deliver, so a rerun redoes them.

        Three faults found in delivered output, none of which the leak gate can see:
          empty     -- the scan came back blank and only the title was written;
          partial   -- far less text than its page count implies (a transcription
                       that stopped early);
          cut-words -- an OCR fragment flagged as a name was cut out of ordinary
                       words ("XXXXXXXحكمة"), which the redactor no longer does.
        Files move to _superseded/ (nothing is deleted) and are marked for retry.
        """
        out = self.settings.output_dir
        token = re.escape(self.settings.replacement_token)
        glued = re.compile(token + r"(?=[ء-ؿف-ي])")
        counts = {"empty": 0, "partial": 0, "cut-words": 0}
        for doc_id, st in self.state.items():
            if st.status != "done":
                continue
            path = out / (doc_id + ".docx")
            if not path.exists():
                continue
            lines = _docx_lines(path)
            text = "\n".join(lines[1:])
            visible = len(re.sub(r"\s", "", text))
            pages = max(1, st.pages)
            if visible < max(EMPTY_MIN_CHARS, EMPTY_MIN_CHARS_PER_PAGE * pages):
                reason = "empty"
            elif pages > 1 and visible / pages < PARTIAL_MAX_CHARS_PER_PAGE:
                reason = "partial"
            elif not self._sidecar(doc_id).exists() and glued.search(text):
                # Only output from before the whole-word rule. A current file can show
                # a full name glued to its neighbour by OCR ("XXXXXXXبمقال") -- that is
                # the intended redaction, and requeuing it would loop forever.
                reason = "cut-words"
            else:
                continue
            dest = out / "_superseded" / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            st.status = "failed"
            st.error = f"requeued: {reason}"
            self.state.update(doc_id, st)
            counts[reason] += 1
        log.info("Requeued for reprocessing: %s", counts)
        return counts


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
