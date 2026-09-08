"""Leak-test release gate (Script.md §2.6 / §4).

An independent, deterministic re-scan of the DELIVERED output for any known PII
string. The gate is intentionally *at least as tolerant* as the redactor, and adds a
second, broader pass, so it can catch a survival the redactor's own matcher would miss:

  1. flex pass  — same whitespace-flexible + Arabic-variant-tolerant regex the redactor
                  uses (catches ordinary survivals, incl. line-wrapped names);
  2. collapsed pass — strip diacritics, tatweel, and ALL whitespace, unify alef/ya, then
                  substring-match (catches diacritic- or whitespace-joined survivals the
                  token regex can't see).

Release rule: **zero hits, or the document is rejected/quarantined.** A false positive
here only sends a clean file to review — a false negative ships a privacy leak, so the
gate is deliberately biased toward catching more.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .redactor import MIN_REDACTABLE_CHARS, _flex_pattern, _variants

# Arabic diacritics (harakat U+0610–U+061A, U+064B–U+065F, superscript alef U+0670)
# and tatweel (U+0640). Explicit code points — a literal char range can span Arabic
# *letters* and silently corrupt words.
_DIAC = re.compile("[ؐ-ؚـً-ٰٟ]")
_ALEF = {ord(c): "ا" for c in "أإآٱ"}  # أ إ آ ٱ -> ا
_YA = {ord("ى"): "ي"}                                 # ى -> ي
# Below this normalized length a substring match is too likely to be a coincidence.
_MIN_COLLAPSED = 4


def _collapse(s: str) -> str:
    s = _DIAC.sub("", s)
    s = s.translate(_ALEF).translate(_YA)
    return re.sub(r"\s+", "", s)


@dataclass
class LeakResult:
    passed: bool
    hits: int = 0
    leaked: List[str] = field(default_factory=list)


def leak_scan(output_text: str, pii_values: List[str]) -> LeakResult:
    """Search `output_text` for any of `pii_values`. Empty hits == passed."""
    leaked: List[str] = []
    hits = 0
    collapsed_out = _collapse(output_text)

    for value in pii_values:
        v = value.strip()
        cv = _collapse(v)
        # Anything the redactor is not allowed to remove must not be reported as a
        # leak either, or every document containing the court's own party initials
        # ("أ. ه.") would be quarantined forever.
        if len(cv) < MIN_REDACTABLE_CHARS:
            continue
        found = 0
        # pass 1: flex regex (same reach as the redactor)
        for variant in _variants(v):
            if variant.strip():
                found = len(_flex_pattern(variant).findall(output_text))
                if found:
                    break
        # pass 2: collapsed substring (broader — catches what the regex can't)
        if not found and len(cv) >= _MIN_COLLAPSED and cv in collapsed_out:
            found = 1
        if found:
            leaked.append(value)
            hits += found

    return LeakResult(passed=(hits == 0), hits=hits, leaked=sorted(set(leaked)))
