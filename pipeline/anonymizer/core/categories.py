"""Court-chamber taxonomy used to classify each document.

The **category** is the chamber, expressed in the short canonical form both briefs use
(Script.md §3, website_brief §S-2):

    إدارية · تجارية · مدنية · جنائية · اجتماعية · أحوال شخصية · عقارية · غير محدد

The model (or a header regex) may return either the short form or a fuller phrase such
as "الغرفة التجارية" / "محكمة الاستئناف الإدارية"; `normalize_category` maps any of them
to the canonical short label so the pipeline and the platform's browse agree.
"""
from __future__ import annotations

import re

UNKNOWN = "غير محدد"  # used when the document can't be classified

# Canonical short categories (the values every output carries), per the briefs.
CATEGORIES: list[str] = [
    "إدارية", "تجارية", "مدنية", "جنائية", "اجتماعية", "أحوال شخصية", "عقارية",
]

# Parent courts (blue header) — context only, never the category value.
COURTS: list[str] = [
    "محكمة النقض", "محكمة الاستئناف التجارية", "محكمة الاستئناف الإدارية",
    "المحكمة الابتدائية", "المحكمة الدستورية", "المجلس الأعلى للحسابات",
]

_TASHKEEL = re.compile("[ؐ-ؚـً-ٰٟ]")  # diacritics + tatweel (explicit code points)


def _normalize(text: str) -> str:
    text = _TASHKEEL.sub("", text or "")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return re.sub(r"\s+", " ", text).strip()


# Normalized trigger substrings -> canonical category. Robust to short/long phrasings
# ("تجارية", "الغرفة التجارية", "محكمة الاستئناف التجارية" all -> "تجارية").
_TRIGGERS: list[tuple[str, str]] = [
    ("ادار", "إدارية"),
    ("تجار", "تجارية"),
    ("اجتماع", "اجتماعية"),
    ("احوال", "أحوال شخصية"),
    ("شخصي", "أحوال شخصية"),
    ("عقار", "عقارية"),
    ("جناي", "جنائية"),
    ("جنائ", "جنائية"),
    ("مدني", "مدنية"),
]


def normalize_category(value: str) -> str:
    """Map a model-returned chamber to the canonical short value, else UNKNOWN."""
    n = _normalize(value)
    if not n:
        return UNKNOWN
    for trigger, canon in _TRIGGERS:
        if trigger in n:
            return canon
    return UNKNOWN
