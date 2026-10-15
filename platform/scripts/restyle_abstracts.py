"""Give the abstract at the top of every delivered file a title and a larger size.

The abstract was set at 12 pt above rulings mostly typeset at 13-14 pt, so it read as
smaller than the text it summarises -- and in the Arabic files only Word's ordinary
size was set, not the separate size Word uses for Arabic script, so it may not have
applied at all. This restyles the files already written; nothing is translated again.

    Arabic   «ملخص القرار» 24 pt bold, centred, then the abstract at 16 pt bold
    French   «Résumé de l'arrêt» 20 pt bold, centred, then the abstract at 13 pt bold

Safe to run twice: a file that already has the title only has the title's size and
placement brought up to date.

    python restyle_abstracts.py --delivery ../../delivery
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

TITLE = {"ar": "ملخص القرار", "fr": "Résumé de l'arrêt"}
TITLE_PT = {"ar": 24, "fr": 20}
ABSTRACT_PT = {"ar": 16, "fr": 13}


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
    if paras[0].text.strip() == TITLE[lang]:
        head = paras[0]
        if head.alignment == WD_ALIGN_PARAGRAPH.CENTER and                 all(r.font.size == Pt(TITLE_PT[lang]) for r in head.runs):
            return path, "already done"
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in head.runs:
            _size(r, TITLE_PT[lang], rtl)
        d.save(path)
        return path, "title updated"
    first = paras[0]
    if not first.text.strip() or not any(r.bold for r in first.runs):
        return path, "first paragraph is not the abstract"

    for r in first.runs:
        _size(r, ABSTRACT_PT[lang], rtl)

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
        if r not in ("restyled", "title updated", "already done"):
            print(f"   e.g. {Path(p).name}: {r}")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
