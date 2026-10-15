"""Give the abstract at the top of every delivered file a title and a larger size.

The abstract was set at 12 pt above rulings mostly typeset at 13-14 pt, so it read as
smaller than the text it summarises -- and in the Arabic files only Word's ordinary
size was set, not the separate size Word uses for Arabic script, so it may not have
applied at all. This restyles the files already written; nothing is translated again.

    Arabic   «ملخص القرار» 24 pt bold, centred, then the abstract at 14 pt bold, justified
    French   «Résumé de l'arrêt» 20 pt bold, centred, then the abstract at 12 pt bold, justified

French files are also laid out like the Arabic ones (see french_layout).

Safe to run twice: a file that already has the title only has the title's and the
abstract's size and alignment brought up to date.

    python restyle_abstracts.py --delivery ../../delivery
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

TITLE = {"ar": "ملخص القرار", "fr": "Résumé de l'arrêt"}
TITLE_PT = {"ar": 24, "fr": 20}
ABSTRACT_PT = {"ar": 14, "fr": 12}


def _size(run, pt: int, rtl: bool) -> None:
    """Set the size Word uses for this script -- both of them, for Arabic."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
    run.font.size = Pt(pt)
    if rtl:
        rpr = run._r.get_or_add_rPr()
        cs = rpr.find(qn("w:szCs"))
        if cs is None:
            cs = OxmlElement("w:szCs")
            rpr.append(cs)
        cs.set(qn("w:val"), str(pt * 2))
        if rpr.find(qn("w:bCs")) is None and run.bold:
            rpr.append(OxmlElement("w:bCs"))

# The French files were plain text in Word's defaults; the Arabic ones carry the
# pipeline's layout (pipeline/anonymizer/documents/docx_writer.py). This gives the
# French the same: Times New Roman, 1.5 spacing, the court line bold and underlined,
# ceremonial one-liners centred in bold, the body justified.
FONT = "Times New Roman"
FR_BODY_PT, FR_HEADING_PT, FR_COURT_PT = 12, 13, 16
FR_CUE = re.compile(
    r"^(Au nom de Sa Majest|Royaume du Maroc|Pour ces (motifs|raisons)|Par ces motifs|"
    r"Cour de cassation|Cour suprême|Conseil supérieur|Arrêts? (n°|de la Cour|numéro)|"
    r"Décision n|Rejet|Cassation|Irrecevab|Le rejet|Annulation|Au fond|Sur la forme|"
    r"Dans la forme|Sur le (moyen|premier|second|deuxième|troisième))", re.I)


def _is_heading(text: str) -> bool:
    return len(text) <= 60 and (len(text) <= 22 or bool(FR_CUE.search(text)))         and not (len(text) > 22 and text.endswith((",", ";")))


def french_layout(d) -> bool:
    """Lay a French file out like its Arabic twin. False if it already is."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH as A
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
    normal = d.styles["Normal"]
    if normal.font.name == FONT:
        return False
    normal.font.name = FONT
    normal.font.size = Pt(FR_BODY_PT)
    rpr = normal.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        fonts.set(qn(attr), FONT)
    for theme in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme"):
        fonts.attrib.pop(qn(theme), None)
    for sec in d.sections:
        sec.top_margin = sec.bottom_margin = Cm(2.5)
        sec.left_margin = sec.right_margin = Cm(2.5)

    paras = d.paragraphs
    i = 0
    if paras and paras[0].text.strip() == TITLE["fr"]:        # skip the abstract block
        i = 2
        while i < len(paras) and paras[i].text.strip():
            i += 1
        while i < len(paras) and not paras[i].text.strip():
            i += 1
    court = True
    for p in paras[i:]:
        text = p.text.strip()
        if not text:
            continue
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        pf.space_after = Pt(6)
        if court:                                              # «Cour de cassation — …»
            p.alignment = A.CENTER
            pf.space_after = Pt(18)
            for r in p.runs:
                r.bold, r.underline, r.font.size = True, True, Pt(FR_COURT_PT)
            court = False
        elif _is_heading(text):
            p.alignment = A.CENTER
            for r in p.runs:
                r.bold, r.font.size = True, Pt(FR_HEADING_PT)
        else:
            p.alignment = A.JUSTIFY
    return True


def restyle(job: tuple) -> tuple:
    path, lang = job
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
    try:
        d = Document(path)
    except Exception as e:
        return path, f"unreadable: {type(e).__name__}"
    paras = d.paragraphs
    if not paras:
        return path, "empty"
    rtl = lang == "ar"

    def fits(p, pt, align):
        return p.alignment == align and all(r.font.size == Pt(pt) for r in p.runs)

    def fix(p, pt, align):
        p.alignment = align
        for r in p.runs:
            _size(r, pt, rtl)

    if paras[0].text.strip() == TITLE[lang]:
        head, body = paras[0], (paras[1] if len(paras) > 1 else None)
        if body is None or not any(r.bold for r in body.runs):
            return path, "no abstract under the title"
        if fits(head, TITLE_PT[lang], WD_ALIGN_PARAGRAPH.CENTER) and                 fits(body, ABSTRACT_PT[lang], WD_ALIGN_PARAGRAPH.JUSTIFY):
            if lang == "fr" and french_layout(d):
                d.save(path)
                return path, "laid out"
            return path, "already done"
        fix(head, TITLE_PT[lang], WD_ALIGN_PARAGRAPH.CENTER)
        fix(body, ABSTRACT_PT[lang], WD_ALIGN_PARAGRAPH.JUSTIFY)
        if lang == "fr":
            french_layout(d)
        d.save(path)
        return path, "updated"

    first = paras[0]
    if not first.text.strip() or not any(r.bold for r in first.runs):
        return path, "first paragraph is not the abstract"
    fix(first, ABSTRACT_PT[lang], WD_ALIGN_PARAGRAPH.JUSTIFY)

    title = d.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(4)
    run = title.add_run(TITLE[lang])
    run.bold = True
    _size(run, TITLE_PT[lang], rtl)
    if rtl:
        ppr = title._p.get_or_add_pPr()
        if ppr.find(qn("w:bidi")) is None:
            ppr.append(OxmlElement("w:bidi"))
        rpr = run._r.get_or_add_rPr()
        if rpr.find(qn("w:rtl")) is None:
            rpr.append(OxmlElement("w:rtl"))
    first._p.addprevious(title._p)
    if lang == "fr":
        french_layout(d)
    d.save(path)
    return path, "restyled"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Title and enlarge the abstract in every file")
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    root = Path(args.delivery)
    jobs = [(str(p), "ar") for p in (root / "ar").rglob("*.docx")] + \
           [(str(p), "fr") for p in (root / "fr").rglob("*.docx")]
    if args.limit:
        jobs = jobs[:args.limit] + jobs[-args.limit:]
    from collections import Counter
    with ProcessPoolExecutor(args.workers) as pool:
        res = list(pool.map(restyle, jobs, chunksize=64))
    c = Counter(r for _, r in res)
    print(f"files: {len(jobs):,}")
    for k, v in c.most_common():
        print(f"   {v:>7,}  {k}")
    for p, r in res:
        if r not in ("restyled", "updated", "laid out", "already done"):
            print(f"   e.g. {Path(p).name}: {r}")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
