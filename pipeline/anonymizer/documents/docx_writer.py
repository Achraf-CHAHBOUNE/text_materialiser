"""Write anonymized text into a polished, unified RTL Arabic .docx.

Layout ("mise en page"):
- Times New Roman, 12 pt body / 16 pt title (set for both Latin and complex-script).
- Bold + underlined, centered title at the top.
- Justified body paragraphs, right-to-left, 1.5 line spacing.
- Comfortable page margins, page break between source pages.

python-docx has no high-level RTL switch, so direction/justification/fonts are set
at the OOXML level. Tweak the constants below to restyle every output at once.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

# ---- unified style knobs (edit these to restyle every output) ----
FONT_NAME = "Times New Roman"
BODY_SIZE = 12          # pt
TITLE_SIZE = 16         # pt
LINE_SPACING = 1.5      # multiple
MARGIN_CM = 2.5

# Characters XML 1.0 forbids — OCR text can carry stray control/NULL bytes that make
# python-docx raise when writing. Strip them (keep tab/newline/carriage-return).
_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _xml_safe(text: str) -> str:
    return _XML_ILLEGAL.sub("", text or "")


def _set_run_props(run, size_pt: int, *, bold: bool = False, underline: bool = False) -> None:
    """Apply font, size, bold/underline and RTL to a run (Latin + complex-script)."""
    run.font.name = FONT_NAME
    run.font.bold = bold
    run.font.underline = underline
    rPr = run._element.get_or_add_rPr()

    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), FONT_NAME)

    half = str(int(size_pt * 2))  # OOXML sizes are in half-points
    for tag in ("w:sz", "w:szCs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            rPr.append(el)
        el.set(qn("w:val"), half)

    if rPr.find(qn("w:rtl")) is None:
        rPr.append(OxmlElement("w:rtl"))  # complex-script run is RTL


def _add_paragraph(doc: Document, text: str, *, align, size: int,
                   bold: bool = False, underline: bool = False):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn("w:bidi")) is None:
        pPr.append(OxmlElement("w:bidi"))  # RTL paragraph
    p.alignment = align
    p.paragraph_format.line_spacing = LINE_SPACING
    text = _xml_safe(text)
    if text:
        _set_run_props(p.add_run(text), size, bold=bold, underline=underline)
    return p


def _apply_base_style(doc: Document) -> None:
    """Set the Normal style so even empty paragraphs share the font/spacing."""
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = Pt(BODY_SIZE)
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), FONT_NAME)


def _set_margins(doc: Document) -> None:
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Cm(MARGIN_CM)
        section.left_margin = section.right_margin = Cm(MARGIN_CM)


def _paragraphs(page_text: str) -> List[str]:
    """Group lines into flowing paragraphs (blank line = paragraph break).

    OCR line breaks are scan-layout artifacts, not real paragraph ends; joining
    them lets Word wrap and JUSTIFY the text properly.
    """
    blocks = re.split(r"\n\s*\n", page_text)
    out = []
    for block in blocks:
        para = " ".join(line.strip() for line in block.split("\n") if line.strip())
        if para:
            out.append(para)
    return out


def write_docx(pages: List[str], out_path: Path, title: str = "") -> None:
    """Write one unified-layout .docx; optional bold/underlined centered title."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    _apply_base_style(doc)
    _set_margins(doc)

    if title:
        _add_paragraph(doc, title, align=WD_ALIGN_PARAGRAPH.CENTER, size=TITLE_SIZE,
                       bold=True, underline=True)
        doc.add_paragraph()  # spacer line under the title

    for page_index, page_text in enumerate(pages):
        for para in _paragraphs(page_text):
            _add_paragraph(doc, para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=BODY_SIZE)
        if page_index < len(pages) - 1:
            br = doc.add_paragraph()
            br.add_run().add_break(WD_BREAK.PAGE)

    doc.save(str(out_path))
