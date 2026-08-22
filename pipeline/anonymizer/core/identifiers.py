"""Normalization + matching helpers for case linkage.

The join keys between court levels are file numbers, decision numbers, dates and
court names — all of which vary in spelling/format across documents. These helpers
canonicalize them so an appeal's reference can be matched to the lower ruling's own
identity reliably, and compute a confidence score for each candidate link.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Arabic combining marks (harakat/tanwin), small high marks, superscript alef,
# and tatweel — WITHOUT touching the letters at U+0621–U+064A.
_AR_DIAC = re.compile("[\u0610-\u061A\u0640\u064B-\u065F\u0670]")


def _strip_diac(s: str) -> str:
    s = _AR_DIAC.sub("", s or "")
    return s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")


# --- file number --------------------------------------------------------------
def canon_file_no(raw: str) -> str:
    """Canonical file number: keep digits, unify separators to '/'. e.g. 4443-8202-2015 -> 4443/8202/2015."""
    if not raw:
        return ""
    s = re.sub(r"[^\d/\-\s]", "", raw)
    s = re.sub(r"[\-\s]+", "/", s.strip())
    s = re.sub(r"/+", "/", s).strip("/")
    return s


def file_components(raw: str) -> frozenset:
    """Order-independent set of numeric components (fuzzy fallback)."""
    return frozenset(re.findall(r"\d+", raw or ""))


# --- date ---------------------------------------------------------------------
def canon_date(raw: str) -> str:
    """Return 'YYYY|min|max' using the 4-digit year + the other two parts (order-agnostic)."""
    nums = re.findall(r"\d+", raw or "")
    if len(nums) < 3:
        return ""
    year = next((n for n in nums if len(n) == 4), None)
    if not year:
        return ""
    others = [n for n in nums if n is not year]
    # take the two parts nearest the year triple
    parts = [n for n in nums if n != year][:2] or ["", ""]
    a, b = sorted(parts)
    return f"{year}|{a}|{b}"


def year_of(raw: str) -> str:
    for n in re.findall(r"\d+", raw or ""):
        if len(n) == 4 and n.startswith(("19", "20")):
            return n
    return ""


# --- court / level ------------------------------------------------------------
_CITIES = [
    "الرباط", "الدار البيضاء", "البيضاء", "مراكش", "فاس", "طنجة", "أكادير", "اكادير",
    "وجدة", "مكناس", "الحسيمة", "العيون", "كلميم", "بني ملال", "سطات", "الرشيدية",
    "تازة", "الناظور", "خريبكة", "سلا", "القنيطرة", "تطوان", "ورزازات", "الجديدة",
]


def normalize_court(name: str) -> str:
    return re.sub(r"\s+", " ", _strip_diac(name or "").replace("ب", " ")).strip()


def city_of(name: str) -> str:
    n = _strip_diac(name or "")
    for c in _CITIES:
        if _strip_diac(c) in n:
            return c
    return ""


def court_to_level(court: str) -> str:
    """Map a court name to its level. Order matters (نقض/استئناف before first-instance)."""
    c = _strip_diac(court or "")
    if "النقض" in c or "المجلس الاعلي" in c:
        return "نقض"
    if "الاستئناف" in c or "الاستناف" in c:
        return "استئناف"
    if "الابتدائية" in c or "الادارية" in c or "التجارية" in c:
        return "ابتدائي"
    return ""


# --- identity / reference records --------------------------------------------
@dataclass
class Ident:
    court: str = ""
    city: str = ""
    decision_no: str = ""
    date: str = ""
    file_no: str = ""

    @property
    def file_norm(self) -> str:
        return canon_file_no(self.file_no)

    @property
    def date_norm(self) -> str:
        return canon_date(self.date)


# --- deterministic local extraction (backstop for LLM inconsistency) ---------
_NUM = r"\d+(?:\s*[/\-–]\s*\d+){0,3}"
_FILE = r"\d+(?:\s*[/\-–]\s*\d+){1,3}"          # needs at least one separator
_DATE = r"\d{1,4}\s*[/\-]\s*\d{1,2}\s*[/\-]\s*\d{1,4}"
_COURT = r"(محكمة النقض|محكمة الاستئناف[^\n،؛.]{0,45}|المحكمة (?:الابتدائية|التجارية|الإدارية)[^\n،؛.]{0,45})"


def _tidy(s: str) -> str:
    return re.sub(r"\s*([/\-–])\s*", r"\1", (s or "").strip())


def _level_from_text(head: str) -> str:
    h = _strip_diac(head)
    if "النقض" in h or "المجلس الاعلي" in h:
        return "نقض"
    if "الاستئناف" in h or "الاستناف" in h:
        return "استئناف"
    if "الابتدائية" in h or "المحكمة التجارية" in h or "المحكمة الادارية" in h:
        return "ابتدائي"
    return ""


def local_extract(text: str) -> tuple[str, Ident, list[Ident]]:
    """Extract (level, own identity, references) from ruling text via regex.

    Used to fill whatever the LLM leaves empty — legal headers are highly regular,
    so this is a reliable, free backstop.
    """
    head = text[:900]
    level = _level_from_text(head)
    mc = re.search(_COURT, head)
    dec = re.search(r"(?:القرار|الحكم|قرار|حكم)\s*(?:عدد|رقم)\s*(" + _NUM + ")", head)
    fil = re.search(r"ملف[^\d\n]{0,20}(?:عدد|رقم)\s*(" + _FILE + ")", head)
    dat = re.search(r"(?:المؤرخ في|بتاريخ|الصادر (?:بتاريخ|في))\s*(" + _DATE + ")", head)
    own_court = mc.group(1).strip() if mc else ""
    own = Ident(
        court=own_court, city=city_of(own_court),
        decision_no=_tidy(dec.group(1)) if dec else "",
        date=_tidy(dat.group(1)) if dat else "",
        file_no=_tidy(fil.group(1)) if fil else "",
    )

    refs: list[Ident] = []
    for m in re.finditer(r"عن\s+" + _COURT, text):
        court = m.group(1).strip()
        ctx = text[max(0, m.start() - 260): m.start()]
        d = re.search(r"(?:القرار|الحكم)\s*(?:رقم|عدد)\s*(" + _NUM + ")", ctx)
        f = re.search(r"الملف\s*(?:عدد|رقم)\s*(" + _FILE + ")", ctx)
        dt = re.search(r"(" + _DATE + ")", ctx)
        refs.append(Ident(
            court=court, city=city_of(court),
            decision_no=_tidy(d.group(1)) if d else "",
            date=_tidy(dt.group(1)) if dt else "",
            file_no=_tidy(f.group(1)) if f else "",
        ))
    return level, own, refs


def match_score(a: Ident, b: Ident) -> tuple[int, str]:
    """Score how strongly reference `a` matches own-identity `b`.

    Returns (score, level). Requires at least a file-number or decision-number
    agreement; court/date add confidence.
    """
    score = 0
    fa, fb = a.file_norm, b.file_norm
    file_hit = bool(fa and fb and fa == fb)
    file_fuzzy = bool(fa and fb and not file_hit and file_components(a.file_no) == file_components(b.file_no))
    dec_hit = bool(a.decision_no and b.decision_no and a.decision_no.strip() == b.decision_no.strip())
    date_hit = bool(a.date_norm and b.date_norm and a.date_norm == b.date_norm)
    year_hit = bool(year_of(a.date) and year_of(a.date) == year_of(b.date))
    court_hit = bool(a.city and b.city and a.city == b.city) or (
        court_to_level(a.court) and court_to_level(a.court) == court_to_level(b.court)
    )

    if file_hit:
        score += 3
    elif file_fuzzy:
        score += 1
    if dec_hit:
        score += 2
    if date_hit:
        score += 1
    if court_hit:
        score += 1

    # A link is only trustworthy with an EXACT file-number match, or with
    # decision-number + date + court all agreeing. Everything weaker (fuzzy
    # file, decision-only, year-only, court-only) is NOT link-worthy — it would
    # false-merge unrelated cases that happen to share a short number.
    link_worthy = file_hit or (dec_hit and date_hit and court_hit)
    if not link_worthy:
        return score, ("low" if score >= 1 else "none")
    if file_hit and (dec_hit or date_hit) and court_hit:
        conf = "high"
    else:
        conf = "medium"
    return score, conf
