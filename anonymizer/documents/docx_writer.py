"""Write anonymized text into an RTL Arabic .docx.

python-docx has no direct RTL switch, so we set it at the OOXML level:
  - paragraph: <w:bidi/> + right alignment
  - run:       <w:rtl/> and a complex-script font (w:rFonts w:cs)
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

ARABIC_FONT = "Arial"
FONT_SIZE = Pt(12)


def _make_rtl(paragraph) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pPr.append(OxmlElement("w:bidi"))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _style_run_rtl(run) -> None:
    rPr = run._element.get_or_add_rPr()
    rPr.append(OxmlElement("w:rtl"))
    # Complex-script font + size so Arabic shapes correctly.
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:cs"), ARABIC_FONT)
    run.font.name = ARABIC_FONT
    run.font.size = FONT_SIZE


def _add_arabic_paragraph(doc: Document, text: str):
    p = doc.add_paragraph()
    _make_rtl(p)
    run = p.add_run(text)
    _style_run_rtl(run)
    return p


def write_docx(pages: List[str], out_path: Path) -> None:
    """Write one .docx; each page's lines become paragraphs, page break between pages."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()

    for page_index, page_text in enumerate(pages):
        for line in page_text.split("\n"):
            # Keep blank lines as empty paragraphs to roughly preserve spacing.
            _add_arabic_paragraph(doc, line.rstrip())
        if page_index < len(pages) - 1:
            br = doc.add_paragraph()
            br.add_run().add_break(WD_BREAK.PAGE)

    doc.save(str(out_path))
