"""Local PII replacement (no LLM here).

Given a page's OCR text and the verbatim PII strings the LLM flagged, replace
EVERY occurrence with the replacement token. We match each value with a single
whitespace-flexible regex: any run of whitespace between the value's words may be
spaces OR newlines. This catches both contiguous matches and values that OCR
wrapped across a line break (e.g. "عبد\\nالعلي القصار"), which a plain string
replace would miss. Values not found at all are recorded as unmatched (audit log).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .llm.base import PIIEntity


@dataclass
class RedactionReport:
    replaced: List[str] = field(default_factory=list)    # values successfully replaced (>=1 hit)
    unmatched: List[str] = field(default_factory=list)   # flagged but not found in text
    total_hits: int = 0


def _ws_insensitive_pattern(value: str) -> re.Pattern:
    """Build a regex matching `value` where any run of whitespace is flexible."""
    parts = [re.escape(tok) for tok in value.split()]
    return re.compile(r"\s+".join(parts))


def redact_text(text: str, entities: List[PIIEntity], token: str) -> tuple[str, RedactionReport]:
    report = RedactionReport()

    # Deduplicate, longest first, so longer values are redacted before any
    # shorter substring of them.
    values = sorted({e.text for e in entities if e.text.strip()}, key=len, reverse=True)

    for value in values:
        # Whitespace-flexible match covers exact spacing AND OCR line-wraps in one
        # pass, replacing every occurrence (so nothing leaks after a partial hit).
        pattern = _ws_insensitive_pattern(value)
        new_text, n = pattern.subn(token, text)
        if n:
            text = new_text
            report.replaced.append(value)
            report.total_hits += n
        else:
            report.unmatched.append(value)

    return text, report
