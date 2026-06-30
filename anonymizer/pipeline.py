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
from typing import List, Optional

from tqdm import tqdm

from .config import Settings
from .core.categories import UNKNOWN, normalize_category
from .core.redactor import redact_text
from .core.state import DocRecord, State
from .documents.docx_writer import write_docx
from .documents.loaders import InputDoc, discover_inputs, iter_work_batches
from .llm.base import DocumentAI, PIIEntity
from .llm.factory import get_provider
from .utils.logging import get_logger

log = get_logger()


@dataclass
class RunOptions:
    limit: Optional[int] = None
    overwrite: bool = False     # reprocess even if output exists / state says done
    resume: bool = True         # skip documents already marked done


class Pipeline:
    def __init__(self, settings: Settings, provider: Optional[DocumentAI] = None):
        self.settings = settings
        self.provider = provider or get_provider(settings)
        self.state = State(settings.state_file)

    def _output_path(self, doc: InputDoc) -> Path:
        return self.settings.output_dir / (doc.doc_id + ".docx")

    def _process_one(self, doc: InputDoc) -> DocRecord:
        """Process a single document end to end. Runs in a worker thread."""
        all_pages: List[str] = []
        in_tok = out_tok = 0
        # A batch's PII list applies to the whole batch, but any single value
        # lives on just one page. So track matches at the document level and
        # only report a value as unmatched if it was found on NO page anywhere.
        flagged_values: set[str] = set()
        matched_values: set[str] = set()
        category = court = ""

        for batch in iter_work_batches(doc, self.settings.pages_per_batch):
            if batch.kind == "image":
                result = self.provider.process_pdf(batch.pdf_bytes)
                pages = _align_pages(result.pages, batch.page_count)  # OCR text
            else:  # "text": we already have the text locally
                result = self.provider.process_text("\n".join(batch.pages))
                pages = batch.pages

            in_tok += result.input_tokens
            out_tok += result.output_tokens
            flagged_values.update(e.text for e in result.pii if e.text.strip())
            # Classification comes from the header pages; take the first batch
            # that produced a usable value.
            if not category and result.category:
                category = normalize_category(result.category)
            if not court and result.court:
                court = result.court

            for page_text in pages:
                clean, report = redact_text(
                    page_text, result.pii, self.settings.replacement_token
                )
                all_pages.append(clean)
                matched_values.update(report.replaced)

        unmatched_values = sorted(flagged_values - matched_values)
        for value in unmatched_values:
            log.warning("[%s] PII flagged but not found in text: %r", doc.doc_id, value)

        out_path = self._output_path(doc)
        write_docx(all_pages, out_path)

        cost = self.settings.estimate_cost(in_tok, out_tok)
        return DocRecord(
            status="done",
            output=str(out_path),
            category=category or UNKNOWN,
            court=court,
            pages=len(all_pages),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost=cost,
            pii_count=len(matched_values),
            unmatched=len(unmatched_values),
            ts=_dt.datetime.now().isoformat(timespec="seconds"),
        )

    def _should_skip(self, doc: InputDoc, opts: RunOptions) -> bool:
        if opts.overwrite:
            return False
        if opts.resume and self.state.is_done(doc.doc_id) and self._output_path(doc).exists():
            return True
        return False

    def run(self, opts: RunOptions) -> dict:
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

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as pool:
            futures = {pool.submit(self._process_one, d): d for d in todo}
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Anonymizing", unit="doc"):
                doc = futures[fut]
                try:
                    record = fut.result()
                    self.state.update(doc.doc_id, record)
                    log.info(
                        "[OK] %s -> %s | %s | %d pages | %d PII | $%.4f%s",
                        doc.doc_id, record.output, record.category or UNKNOWN,
                        record.pages, record.pii_count, record.cost,
                        f" | {record.unmatched} unmatched" if record.unmatched else "",
                    )
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

        # Side mission: write the file -> category index for every done document.
        index_path = self.settings.output_dir / "index.csv"
        n = self.state.export_index(index_path)
        log.info("Wrote category index: %s (%d documents)", index_path, n)

        return self.state.totals()


def _align_pages(pages: List[str], expected: int) -> List[str]:
    """Make the OCR page list length match the batch's actual page count."""
    if len(pages) == expected:
        return pages
    if len(pages) < expected:
        return pages + [""] * (expected - len(pages))
    return pages[:expected]
