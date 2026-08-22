"""Import-gate PII detector (website_brief §I-2).

The platform must NOT trust that imported files are clean, but it also never receives
the pipeline's list of known PII (that raw data must never enter the platform). So this
gate detects PII *patterns* — the shapes personal data takes — independently:

  - email addresses
  - Moroccan phone numbers (+212 / 0[5-7]xxxxxxxx)
  - national ID (CIN/CNIE): 1–2 letters + 5–6 digits
  - IBAN / long bank-account-like runs

It deliberately does NOT flag bare digit groups (decision/file numbers, dates, amounts,
law articles are legitimate). A hit means the file is refused or quarantined at import.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

_PATTERNS = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?:\+212|00212|0)\s?[5-7](?:[\s.\-]?\d){8}\b")),
    ("national_id", re.compile(r"\b[A-Za-z]{1,2}\s?\d{5,6}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?\d){16,24}\b")),
]


@dataclass
class GateFinding:
    type: str
    value: str


def scan(text: str) -> List[GateFinding]:
    """Return PII-pattern findings in `text` (empty == clean)."""
    findings: List[GateFinding] = []
    seen: set[tuple[str, str]] = set()
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            v = m.group(0).strip()
            key = (kind, v)
            if key not in seen:
                seen.add(key)
                findings.append(GateFinding(kind, v))
    return findings
