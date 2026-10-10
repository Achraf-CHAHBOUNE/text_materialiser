"""Everything one ruling can tell us, read in a single pass.

This used to be four jobs run one after another - import the folder, read the
headnotes, ask a model for the missing ones, fold the proposals back in - each
re-reading the same 29,000 files. A ruling is opened once here and everything that can
be learned from it is learned at once:

    text        the anonymized wording, and whether the PII gate passes it
    subject     the subject the court filed it under, and the keyword chain
    rule        the legal rule the court printed: its own abstract
    outcome     رفض الطلب / نقض وإحالة / ... , from the heading or the closing

Reading the source court's city from the text was tried and dropped: of the 1,948
rulings whose metadata has no city, not one names a court of appeal in a way that
resolves to a real city. The phrase is there often enough -- محكمة الاستئناف بتأييد
الحكم -- but the word after it is a verb, not a place.

Everything here reads what the court wrote. Nothing is invented, and a field the
ruling does not carry comes back empty rather than guessed - `enrich` is where a model
is asked to fill those, and what it writes is kept apart and labelled.
"""
from __future__ import annotations

import re
from typing import NamedTuple

import headnotes
import piigate
import textextract

# What the court decides, in the words it uses. Several spellings of one decision are
# folded onto the first form, so a listing can group by it.
OUTCOMES = {
    "رفض الطلب": ("رفض الطلب", "رفض طلب النقض", "برفض الطلب"),
    "نقض وإحالة": ("نقض وإحالة", "نقض و إحالة", "بنقض وإحالة"),
    "نقض وإبطال": ("نقض وإبطال", "بنقض وإبطال"),
    "نقض جزئي": ("نقض جزئي", "نقض جزئيا"),
    "نقض بدون إحالة": ("نقض بدون إحالة", "نقض بدون احالة"),
    "عدم القبول": ("عدم القبول", "عدم قبول الطلب", "بعدم قبول الطلب", "بعدم القبول"),
    "تسجيل التنازل": ("تسجيل التنازل", "بتسجيل التنازل", "تسجيل تنازل"),
    "عدم الاختصاص": ("عدم الاختصاص", "بعدم الاختصاص"),
    "التشطيب على القضية": ("التشطيب على القضية", "بالتشطيب على القضية"),
}
# the heading form: a line that is the decision and nothing else
_HEADING = re.compile(
    r"^(?:" + "|".join(re.escape(v) for vs in OUTCOMES.values() for v in vs) + r")\s*[.؛]?$")
# the closing form: "لهذه الأسباب ... قضت محكمة النقض بـ..."
_CLOSING_FROM = re.compile(r"لهذه الأسباب|قضت محكمة النقض")
_MARKS = re.compile(r"[ـً-ْٰ‏‎]")

HEAD_LINES = 14          # the heading, if there is one, is near the top
TAIL_CHARS = 2500        # the closing is at the very end


class Extracted(NamedTuple):
    text: str
    clean: bool                      # the PII gate passed it
    theme: str
    sub: list
    qualifier: str
    rule: str
    keywords: str
    outcome: str
    error: str


def _canonical(found: str) -> str:
    found = _MARKS.sub("", found).strip(" .؛:")
    for canon, forms in OUTCOMES.items():
        if found in forms or found == canon:
            return canon
    return ""


def outcome(text: str) -> str:
    """What the court decided.

    Printed twice in most rulings and in neither in some: as a heading of its own near
    the top, and again in the closing after لهذه الأسباب. Reading both covers 77% of
    the corpus where the heading alone covers 32%.
    """
    lines = [_MARKS.sub("", l).strip() for l in text.split("\n") if l.strip()]
    for line in lines[:HEAD_LINES]:
        if _HEADING.match(line):
            got = _canonical(line)
            if got:
                return got

    tail = _MARKS.sub("", text[-TAIL_CHARS:])
    if not _CLOSING_FROM.search(tail):
        return ""
    # whichever decision the court states first in its closing is the one it reached
    best, where = "", len(tail) + 1
    for form, canon in ((v, c) for c, vs in OUTCOMES.items() for v in vs):
        at = tail.find(form)
        if at != -1 and at < where:
            best, where = canon, at
    return best


def read(name: str, data: bytes) -> Extracted:
    """Open one ruling and take everything it carries."""
    empty = Extracted("", False, "", [], "", "", "", "", "")
    try:
        text = textextract.extract(name, data)
    except Exception as e:                        # a damaged file must not stop a run
        return empty._replace(error=f"{type(e).__name__}: {e}")

    note = headnotes.read(text)
    chain = []
    if note:
        chain = [note.theme, *note.sub] + ([note.qualifier] if note.qualifier else [])
    return Extracted(
        text=text,
        clean=not piigate.scan(text),
        theme=note.theme if note else "",
        sub=list(note.sub) if note else [],
        qualifier=note.qualifier if note else "",
        rule=note.rule if note else "",
        keywords=" - ".join(chain),
        outcome=outcome(text),
        error="",
    )


def fields(got: Extracted) -> dict:
    """The columns a ruling's row takes from what was read."""
    return {
        "theme": got.theme,
        "theme_key": headnotes.normalise(got.theme) if got.theme else "",
        "theme_source": "court" if got.theme else "",
        "keywords": got.keywords,
        "rule": got.rule,
        "outcome": got.outcome,
    }
