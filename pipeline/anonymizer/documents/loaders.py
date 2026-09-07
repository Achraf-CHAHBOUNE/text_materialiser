"""Unified input discovery + batching for .pdf, .docx and legacy .doc.

Each input becomes a stream of WorkBatch objects of one of two kinds:
  - "image": scanned PDF pages -> needs vision OCR (provider.process_pdf)
  - "text" : text we extracted locally (.doc/.docx, or PDF with a real text layer)
             -> provider.process_text (PII + classification only, no OCR cost)

A PDF is treated as "text" when its embedded text layer is dense enough; otherwise
it's treated as a scan. .docx is always text; legacy binary .doc is converted to
.docx via LibreOffice first.
"""
from __future__ import annotations

import io
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List

from docx import Document as _DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader, PdfWriter

from .convert import convert_to_docx

# Average extractable chars/page at/above which a PDF is considered "text" (not a scan).
TEXT_PDF_MIN_CHARS_PER_PAGE = 50

SUPPORTED_EXTS = {".pdf", ".docx", ".doc"}


@dataclass
class InputDoc:
    doc_id: str   # path relative to input dir, without extension (output filename)
    path: Path
    ext: str      # ".pdf" | ".docx" | ".doc"


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


# Legacy duplicate of shape/textbox content (mc:Choice already holds the modern copy).
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _walk_paragraph_texts(root, doc) -> List[str]:
    """Every paragraph's text anywhere under `root` — including TEXT BOXES / shapes.

    python-docx's `.paragraphs` only sees top-level body paragraphs, so documents
    that put their content in text boxes (common in these court templates) come out
    empty. Walking the XML tree for all <w:p> captures body, tables AND text boxes.
    We skip <mc:Fallback> so text boxes aren't counted twice.
    """
    out: List[str] = []

    def walk(el):
        for child in el:
            if child.tag == _MC_FALLBACK:
                continue  # legacy duplicate of the modern (mc:Choice) content
            if child.tag == qn("w:p"):
                t = Paragraph(child, doc).text.strip()
                if t:
                    out.append(t)
            walk(child)

    try:
        walk(root)
    except Exception:
        pass
    return out


def _docx_lines(path: Path) -> List[str]:
    """Extract docx text: header + body + footer, including text boxes/shapes.

    Header/footer matter because the case file number (رقم الملف) often lives in a
    header box; text boxes matter because some templates put the whole ruling there.
    """
    doc = _DocxDocument(str(path))
    lines: List[str] = []
    for section in doc.sections:
        lines += _walk_paragraph_texts(section.header._element, doc)
    lines += _walk_paragraph_texts(doc.element.body, doc)
    for section in doc.sections:
        lines += _walk_paragraph_texts(section.footer._element, doc)

    # collapse consecutive duplicates (e.g. repeated header across sections)
    dedup: List[str] = []
    for ln in lines:
        if not dedup or dedup[-1] != ln:
            dedup.append(ln)
    return dedup


def _pdf_slice_bytes(reader: PdfReader, start: int, end: int) -> bytes:
    writer = PdfWriter()
    for i in range(start, end):
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def iter_work_batches(doc: InputDoc, pages_per_batch: int, soffice_path: str = "") -> Iterator[WorkBatch]:
    if doc.ext in (".docx", ".doc"):
        if doc.ext == ".doc":
            # Legacy binary .doc -> convert to .docx (LibreOffice) in a temp dir.
            with tempfile.TemporaryDirectory() as tmp:
                docx_path = convert_to_docx(doc.path, soffice_path, Path(tmp))
                text = "\n".join(_docx_lines(docx_path))
        else:
            text = "\n".join(_docx_lines(doc.path))
        yield WorkBatch(kind="text", pages=[text], page_count=1)
        return

    # PDF: decide text vs scan from the embedded text layer.
    # Only SAMPLE the first few pages — extract_text() parses the whole page content
    # stream and is the single most expensive local step; a document is uniformly a
    # scan or a text PDF in practice, so sampling is enough and much cheaper.
    reader = PdfReader(str(doc.path))
    total = len(reader.pages) or 1
    sample = reader.pages[:min(3, total)]
    sample_texts = [(pg.extract_text() or "") for pg in sample]
    avg_chars = sum(len(t.strip()) for t in sample_texts) / max(1, len(sample_texts))

    if avg_chars >= TEXT_PDF_MIN_CHARS_PER_PAGE:
        # Text PDF: use the local text, batch by page count. Extract the rest now.
        page_texts = list(sample_texts) + [
            (pg.extract_text() or "") for pg in reader.pages[len(sample_texts):]
        ]
        for start in range(0, total, pages_per_batch):
            chunk = page_texts[start : start + pages_per_batch]
            yield WorkBatch(kind="text", pages=chunk, page_count=len(chunk))
    else:
        # Scanned PDF: send page-image slices to the vision model.
        # Fast path: the whole document fits in one batch, so send the original bytes
        # instead of re-encoding it through PdfWriter (pure CPU work under the GIL).
        if total <= pages_per_batch:
            yield WorkBatch(kind="image", pdf_bytes=doc.path.read_bytes(), page_count=total)
            return
        for start in range(0, total, pages_per_batch):
            end = min(start + pages_per_batch, total)
            yield WorkBatch(
                kind="image",
                pdf_bytes=_pdf_slice_bytes(reader, start, end),
                page_count=end - start,
            )
