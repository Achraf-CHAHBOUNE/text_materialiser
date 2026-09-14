"""The four fields a court-portal listing shows for each ruling.

A cassation ruling is browsed as Court -> Chamber -> Year -> row, and every row
carries the decision number, its date, the city and the chamber (the layout of
JURISMAROC, which the client wants mirrored). The model extracts raw versions of
these, but in shapes no listing can use directly:

  - decision numbers arrive as "33/1" (decision/panel section) or "2/96";
  - dates arrive as "08 فبراير 2022", "18 /07 /2016", or OCR-mangled month names;
  - the chamber the model reports is the ruling's *topic*, not the chamber that
    issued it (child support reads as "social"), which mislabelled ~7% of a
    personal-status corpus;
  - the ruling's own city is always Rabat -- the Court of Cassation sits only
    there -- so the city a listing shows is the lower court the appeal came from.

Everything here is deterministic and reads only text the pipeline already has, so
it can be re-applied to past output without another model call.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import re
from typing import Iterable, Optional, Tuple

# --- normalisation -------------------------------------------------------------
_DIAC = re.compile("[ؐ-ؚـً-ٰٟ]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# Persian look-alikes OCR produces for Arabic letters ("بریل" for "بريل").
_LOOKALIKE = str.maketrans({"ی": "ي", "ک": "ك", "ە": "ه", "ۀ": "ه"})
_AR_LETTER = "ء-ي"


def _norm(s: str) -> str:
    s = _DIAC.sub("", s or "").translate(_DIGITS).translate(_LOOKALIKE)
    for a in "أإآٱ":
        s = s.replace(a, "ا")
    return re.sub(r"\s+", " ", s.replace("ى", "ي")).strip()


# --- decision number -----------------------------------------------------------
def display_decision_no(raw: str) -> str:
    """The bare decision number a listing shows ("58"), or "" if none is usable.

    "33/1" and "2/96" pair the decision with the panel section; the section is the
    single-digit side (checked against 142 filenames that carry the true number:
    the multi-digit side matched in all but 5). A value shaped like a file number
    ("2019/1/2/669") was put in the wrong field and is rejected rather than shown.
    """
    s = _norm(str(raw or ""))
    if not s or s.lower() in ("none", "null", "nan", "-"):
        return ""
    s = re.sub(r"\s*/\s*", "/", s)
    if re.fullmatch(r"\d+", s):
        return str(int(s))
    m = re.fullmatch(r"(\d+)/(\d+)", s)
    if m:
        a, b = m.group(1), m.group(2)
        if len(a) == 1 and len(b) > 1:
            return str(int(b))
        return str(int(a))
    return ""


# --- date ----------------------------------------------------------------------
_MONTHS = {
    "يناير": 1, "جانفي": 1, "فبراير": 2, "فيفري": 2, "مارس": 3, "ابريل": 4, "بريل": 4,
    "افريل": 4, "ماي": 5, "مايو": 5, "يونيو": 6, "يونيه": 6, "جوان": 6, "يوليوز": 7,
    "يوليو": 7, "يوليه": 7, "جويلية": 7, "غشت": 8, "اغسطس": 8, "اوت": 8, "شتنبر": 9,
    "سبتمبر": 9, "اكتوبر": 10, "نونبر": 11, "نوفمبر": 11, "دجنبر": 12, "ديسمبر": 12,
}
_MONTH_NAMES = list(_MONTHS)


def _month(word: str) -> Optional[int]:
    w = re.sub(f"[^{_AR_LETTER}]", "", _norm(word))
    if not w:
        return None
    if w in _MONTHS:
        return _MONTHS[w]
    # OCR damage ("وجنبر" for "دجنبر"). A close match only -- Hijri month names are
    # far from every Gregorian one and must not be coerced into a false date.
    close = difflib.get_close_matches(w, _MONTH_NAMES, n=1, cutoff=0.8)
    return _MONTHS[close[0]] if close else None


def _valid(d: int, m: int, y: int) -> bool:
    """A real calendar date in a plausible range (so 31 February is rejected)."""
    if not 1900 <= y <= 2100:
        return False
    try:
        _dt.date(y, m, d)
    except ValueError:
        return False
    return True


def display_date(raw: str) -> str:
    """The ruling date as DD/MM/YYYY, or "" if no complete Gregorian date is present."""
    s = _norm(str(raw or ""))
    if not s:
        return ""
    for m in re.finditer(rf"(?<!\d)(\d{{1,2}})\s*[^\d\s]?\s*([{_AR_LETTER}(]+)\s*(\d{{4}})(?!\d)", s):
        month = _month(m.group(2))
        d, y = int(m.group(1)), int(m.group(3))
        if month and _valid(d, month, y):
            return f"{d:02d}/{month:02d}/{y}"
    for m in re.finditer(r"(?<!\d)(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?!\d)", s):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid(d, mo, y):
            return f"{d:02d}/{mo:02d}/{y}"
    for m in re.finditer(r"(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})(?!\d)", s):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid(d, mo, y):
            return f"{d:02d}/{mo:02d}/{y}"
    return ""


def header_date(text: str) -> str:
    """The decision date from the ruling's own header ("الصادر بتاريخ 08 فبراير 2022").

    A last resort when neither the model nor the numeric regex produced one: the
    first date after "بتاريخ" near the top is the ruling's own.
    """
    head = _norm(text)[:CHAMBER_HEAD_CHARS]
    m = re.search(r"بتاريخ\s*[:：]?", head)
    return display_date(head[m.end(): m.end() + 40]) if m else ""


# --- chamber -------------------------------------------------------------------
# The file type a ruling states about itself ("في الملف الشرعي رقم ...") names the
# chamber that issued it. Measured on 600 rulings: present in the header of 96.5%.
_FILE_TYPE = {
    "شرعي": "أحوال شخصية", "مدني": "مدنية", "اجتماعي": "اجتماعية", "تجاري": "تجارية",
    "عقاري": "عقارية", "اداري": "إدارية", "جنحي": "جنائية", "جنائي": "جنائية",
}
_ROOM = {
    "الشرعية": "أحوال شخصية", "الاحوال الشخصية": "أحوال شخصية", "المدنية": "مدنية",
    "الاجتماعية": "اجتماعية", "التجارية": "تجارية", "العقارية": "عقارية",
    "الادارية": "إدارية", "الجنائية": "جنائية",
}
_FILE_RX = re.compile(r"(?:^|[^" + _AR_LETTER + r"])(?:ال)?ملف\s+(?:ال)?(" + "|".join(_FILE_TYPE) + ")")
_ROOM_RX = re.compile(r"(?:^|[^" + _AR_LETTER + r"])(?:ال)?غرفة\s+(" + "|".join(_ROOM) + ")")
CHAMBER_HEAD_CHARS = 900


def chamber_from_text(text: str) -> str:
    """The issuing chamber as stated in the ruling's header, or "" if it says none.

    Only the header is read: further down, a ruling can mention the lower court's
    file ("الملف المدني عدد ...") whose type is not this chamber's.
    """
    head = _norm(text)[:CHAMBER_HEAD_CHARS]
    hits = []
    for rx, table in ((_FILE_RX, _FILE_TYPE), (_ROOM_RX, _ROOM)):
        m = rx.search(head)
        if m:
            hits.append((m.start(), table[m.group(1)]))
    return min(hits)[1] if hits else ""


# --- city ----------------------------------------------------------------------
# Seats of Morocco's appeal and first-instance courts. Canonical spelling first,
# then variants seen in rulings (normalised on comparison, so hamza forms and
# alef-maqsura need not be listed).
_CITY_VARIANTS = {
    "الرباط": ["الرباط", "رباط"],
    "الدار البيضاء": ["الدار البيضاء", "الدارالبيضاء", "البيضاء"],
    "فاس": ["فاس"], "مكناس": ["مكناس"], "مراكش": ["مراكش"], "أكادير": ["أكادير"],
    "طنجة": ["طنجة"], "تطوان": ["تطوان"], "وجدة": ["وجدة"], "القنيطرة": ["القنيطرة"],
    "الجديدة": ["الجديدة"], "سطات": ["سطات"], "بني ملال": ["بني ملال", "بنى ملال"],
    "خريبكة": ["خريبكة"], "آسفي": ["آسفي", "أسفي"], "ورزازات": ["ورزازات"],
    "الرشيدية": ["الرشيدية"], "تازة": ["تازة"], "الحسيمة": ["الحسيمة"],
    "الناظور": ["الناظور"], "العيون": ["العيون"], "كلميم": ["كلميم", "گلميم"],
    "العرائش": ["العرائش"], "سلا": ["سلا"], "تمارة": ["تمارة"], "الخميسات": ["الخميسات"],
    "المحمدية": ["المحمدية"], "بن سليمان": ["بن سليمان", "بنسليمان", "ابن سليمان"], "برشيد": ["برشيد"],
    "سيدي بنور": ["سيدي بنور"], "اليوسفية": ["اليوسفية"], "الصويرة": ["الصويرة"],
    "شيشاوة": ["شيشاوة"], "قلعة السراغنة": ["قلعة السراغنة"], "ابن جرير": ["ابن جرير", "بن جرير"],
    "إنزكان": ["إنزكان"], "تارودانت": ["تارودانت"], "تزنيت": ["تزنيت"], "طاطا": ["طاطا"],
    "طانطان": ["طانطان"], "السمارة": ["السمارة"], "الداخلة": ["الداخلة"], "بوجدور": ["بوجدور"],
    "صفرو": ["صفرو"], "بولمان": ["بولمان"], "تاونات": ["تاونات"], "الحاجب": ["الحاجب"],
    "إفران": ["إفران"], "ميدلت": ["ميدلت"], "خنيفرة": ["خنيفرة"], "أزرو": ["أزرو"],
    "الفقيه بن صالح": ["الفقيه بن صالح"], "قصبة تادلة": ["قصبة تادلة"], "أزيلال": ["أزيلال"],
    "وادي زم": ["وادي زم"], "أبي الجعد": ["أبي الجعد"], "زاكورة": ["زاكورة"], "تنغير": ["تنغير"],
    "بوعرفة": ["بوعرفة"], "فجيج": ["فجيج"], "جرادة": ["جرادة"], "تاوريرت": ["تاوريرت"],
    "بركان": ["بركان"], "الدريوش": ["الدريوش"], "القصر الكبير": ["القصر الكبير"],
    "أصيلة": ["أصيلة", "أصيلا"], "شفشاون": ["شفشاون"], "وزان": ["وزان"],
    "سيدي قاسم": ["سيدي قاسم"], "سيدي سليمان": ["سيدي سليمان"],
    "سوق أربعاء الغرب": ["سوق أربعاء الغرب", "سوق الاربعاء"], "تيفلت": ["تيفلت"],
    "الرماني": ["الرماني"], "سيدي إفني": ["سيدي إفني"], "الصخيرات": ["الصخيرات"], "جرسيف": ["جرسيف", "كرسيف"],
}
# Longest first, so "الدار البيضاء" wins over its tail "البيضاء".
_CITY_INDEX = sorted(
    ((_norm(v), canon) for canon, vs in _CITY_VARIANTS.items() for v in vs),
    key=lambda x: -len(x[0]),
)
# A city stands alone or behind a one-letter clitic ("بالرباط", "ببني ملال"), never
# inside another word -- "سلا" must not match "الإسلامية".
_CITY_RX = [
    (re.compile(r"(?:^|[^" + _AR_LETTER + r"])[بلوف]?" + re.escape(v) + r"(?![" + _AR_LETTER + r"])"), c)
    for v, c in _CITY_INDEX
]


def canonical_city(text: str) -> str:
    """The first known court seat named in `text`, in canonical spelling."""
    n = _norm(text)
    if not n:
        return ""
    best = None
    for rx, canon in _CITY_RX:
        m = rx.search(n)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), canon)
    return best[1] if best else ""


# Court levels are judged with the spaces taken out: OCR splits these words
# ("محكمة ال ستئناف", "المحكمة الا بتدائية") often enough to matter.
def _court_kind(court: str) -> str:
    c = _norm(court).replace(" ", "")
    if "النقض" in c or "المجلسالاعلي" in c:
        return "top"
    if re.search(r"ست[ئي]?ناف", c):
        return "appeal"
    if "بتدائي" in c or "المركزالقضائي" in c or c.endswith(("التجارية", "الادارية")):
        return "first-instance"
    return "unknown"


_APPEAL_IN_TEXT = re.compile(r"محكمة\s*ال\s*ا?\s*ست\s*[ئي]?\s*ناف")


def origin_city(refs: Iterable, text: str = "") -> Tuple[str, str]:
    """(city, source) of the lower court a cassation ruling reviews.

    Prefers the appeal court the ruling names, then a first-instance court, taken
    from the references already extracted; failing both, the first appeal court
    named anywhere in the text. References to the Court of Cassation itself (a
    ruling remanded or cited) are not origins and are skipped.
    """
    ranked = {"appeal": [], "first-instance": [], "unknown": []}
    for r in refs:
        court = getattr(r, "court", "") or ""
        kind = _court_kind(court)
        if kind == "top":
            continue
        city = canonical_city(getattr(r, "city", "") or "") or canonical_city(court)
        if city:
            ranked[kind].append(city)
    for kind in ("appeal", "first-instance", "unknown"):
        if ranked[kind]:
            return ranked[kind][0], (kind if kind != "unknown" else "reference")
    n = _norm(text)
    for m in _APPEAL_IN_TEXT.finditer(n):
        city = canonical_city(n[m.end(): m.end() + 40])
        if city:
            return city, "appeal-in-text"
    return "", ""
