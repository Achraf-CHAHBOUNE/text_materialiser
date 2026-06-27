"""Court-chamber taxonomy used to classify each document.

From the reference image: each blue header is a COURT, each black row under it is
a CHAMBER. The required "category" is the black-text chamber name. We keep the
parent court too (helps disambiguate the two identical "الغرفة الاستئنافية" rows
and is handy in the index), but the category value itself is always black text.
"""
from __future__ import annotations

import re

# (court [blue], chamber [black])
TAXONOMY: list[tuple[str, str]] = [
    ("محكمة النقض", "غرفة الأحوال الشخصية"),
    ("محكمة النقض", "الغرفة التجارية"),
    ("محكمة النقض", "الغرفة الإجتماعية"),
    ("محكمة النقض", "الغرفة العقارية"),
    ("محكمة النقض", "الغرفة الجنائية"),
    ("محكمة النقض", "الغرفة المدنية"),
    ("محكمة النقض", "الغرفة الإدارية"),
    ("محكمة الاستئناف التجارية", "الغرفة الاستئنافية"),
    ("محكمة الاستئناف الإدارية", "الغرفة الاستئنافية"),
    ("المحكمة الدستورية", "الغرفة الدستورية"),
    ("المجلس الأعلى للحسابات", "المجلس الأعلى للحسابات"),
]

# Distinct black-text categories the model may return.
CATEGORIES: list[str] = list(dict.fromkeys(chamber for _, chamber in TAXONOMY))
COURTS: list[str] = list(dict.fromkeys(court for court, _ in TAXONOMY))

UNKNOWN = "غير محدد"  # used when the document can't be classified

_TASHKEEL = re.compile(r"[ؗ-ًؚ-ْٰـ]")  # diacritics + tatweel


def _normalize(text: str) -> str:
    text = _TASHKEEL.sub("", text or "")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    return re.sub(r"\s+", " ", text).strip()


_CATEGORY_LOOKUP = {_normalize(c): c for c in CATEGORIES}


def normalize_category(value: str) -> str:
    """Map a model-returned chamber to the canonical black-text value, else UNKNOWN."""
    return _CATEGORY_LOOKUP.get(_normalize(value), UNKNOWN if value else UNKNOWN)
