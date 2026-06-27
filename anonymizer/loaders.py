"""Unified input discovery + batching for .pdf and .docx.

Each input becomes a stream of WorkBatch objects of one of two kinds:
  - "image": scanned PDF pages -> needs vision OCR (provider.process_pdf)
  - "text" : text we extracted locally (.docx, or PDF with a real text layer)
             -> provider.process_text (PII + classification only, no OCR cost)

A PDF is treated as "text" when its embedded text layer is dense enough; otherwise
it's treated as a scan. .docx is always text.
"""
from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List

from docx import Document as _DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader, PdfWriter

# Average extractable chars/page at/above which a PDF is considered "text" (not a scan).
TEXT_PDF_MIN_CHARS_PER_PAGE = 50

SUPPORTED_EXTS = {".pdf", ".docx"}


@dataclass
class InputDoc:
    doc_id: str   # path relative to input dir, without extension (output filename)
    path: Path
    ext: str      # ".pdf" | ".docx"


@dataclass
class WorkBatch:
    kind: str                              # "image" | "text"
    pages: List[str] = field(default_factory=list)  # text pages (text kind)
    pdf_bytes: bytes = b""                  # PDF slice (image kind)
    page_count: int = 0


def discover_inputs(input_dir: Path) -> List[InputDoc]:
    files = [
        p
        for p in sorted(input_dir.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTS
        and not p.name.startswith("~$")  # Word lock/temp files
    ]
    # If a .pdf and .docx share the same stem, keep the extension in the id so
    # their outputs/state don't collide; otherwise use the clean stem.
    stems = Counter(p.relative_to(input_dir).with_suffix("").as_posix() for p in files)

    docs: List[InputDoc] = []
    for p in files:
        stem_id = p.relative_to(input_dir).with_suffix("").as_posix()
        doc_id = stem_id if stems[stem_id] == 1 else stem_id + p.suffix.lower().replace(".", "_")
        docs.append(InputDoc(doc_id=doc_id, path=p, ext=p.suffix.lower()))
    return docs


def _docx_lines(path: Path) -> List[str]:
    """Extract docx text in document order (paragraphs + table rows)."""
    doc = _DocxDocument(str(path))
    lines: List[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            lines.append(Paragraph(child, doc).text)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, doc).rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append("  ".join(cells))
    return lines


def _pdf_slice_bytes(reader: PdfReader, start: int, end: int) -> bytes:
    writer = PdfWriter()
    for i in range(start, end):
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def iter_work_batches(doc: InputDoc, pages_per_batch: int) -> Iterator[WorkBatch]:
    if doc.ext == ".docx":
        text = "\n".join(_docx_lines(doc.path))
        yield WorkBatch(kind="text", pages=[text], page_count=1)
        return

    # PDF: decide text vs scan from the embedded text layer.
    reader = PdfReader(str(doc.path))
    page_texts = [(pg.extract_text() or "") for pg in reader.pages]
    total = len(page_texts) or 1
    avg_chars = sum(len(t.strip()) for t in page_texts) / total

    if avg_chars >= TEXT_PDF_MIN_CHARS_PER_PAGE:
        # Text PDF: use the local text, batch by page count.
        for start in range(0, total, pages_per_batch):
            chunk = page_texts[start : start + pages_per_batch]
            yield WorkBatch(kind="text", pages=chunk, page_count=len(chunk))
    else:
        # Scanned PDF: send page-image slices to the vision model.
        for start in range(0, total, pages_per_batch):
            end = min(start + pages_per_batch, total)
            yield WorkBatch(
                kind="image",
                pdf_bytes=_pdf_slice_bytes(reader, start, end),
                page_count=end - start,
            )
