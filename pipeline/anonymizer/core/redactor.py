"""Local PII replacement (no LLM here).

Given the text and the verbatim PII strings the LLM flagged, replace EVERY occurrence
with the replacement token. Matching is deliberately tolerant to maximise recall (a
missed name is a privacy leak):

- character-by-character with optional "noise" between letters — whitespace (so OCR
  line-wraps match), tatweel, and diacritics — so "عبد السلام" and "عبدالسلام" and a
  harakat-laden spelling all match the same flagged value;
- Arabic-variant-tolerant: alef forms (أ إ آ ا ٱ) and ya/alef-maqsura (ي ى) are treated
  as equivalent;
- honorific fallback: if a flagged value carries a courtesy title (السيد، الأستاذ…) that
  isn't in the text, we retry with the title stripped.

Values that still can't be located are recorded as unmatched (audit log).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List

from ..llm.base import PIIEntity

# Courtesy titles that may prefix a name in the model output but not the text.
HONORIFICS = (
    "السيد", "السيدة", "الأستاذ", "الأستاذة", "الاستاذ", "الاستاذة",
    "المستشار", "المستشارة", "الدكتور", "الدكتورة", "الحاج", "الحاجة",
    "الأستاذين", "السادة", "مولاي",
)

# Below this many significant characters a value cannot be matched safely: it would
# hit fragments of ordinary words and shred the document. In practice these are the
# court's OWN initials for the parties ("أ. ه."), which are already de-identified —
# so they are neither redacted nor treated as leaks. The leak gate imports this same
# constant so the two never drift apart.
MIN_REDACTABLE_CHARS = 3

# Interchangeable Arabic letters (key char -> all equivalent forms).
_EQUIV = {c: "اأإآٱ" for c in "اأإآٱ"}
_EQUIV.update({c: "يى" for c in "يى"})

# Allowed "noise" between two significant characters of a name: whitespace (incl. OCR
# line-wraps), tatweel (U+0640), harakat (U+064B–U+065F), superscript alef (U+0670).
_BETWEEN = "[\\sـً-ٰٟ]*"
# The same characters, as a matcher for stripping them out of a flagged value.
# The model echoes a name exactly as the OCR rendered it, tatweel and all
# ("باســــــو"), and requiring those decorations to reappear in the
# same places made the pattern miss the plain spelling. They are noise wherever
# they occur, so they are dropped from the value and tolerated in the text.
_NOISE = re.compile("[\\sـً-ٰٟ]")


@dataclass
class RedactionReport:
    replaced: List[str] = field(default_factory=list)    # values successfully replaced (>=1 hit)
    unmatched: List[str] = field(default_factory=list)   # flagged but not found in text
    total_hits: int = 0


def _char_class(ch: str) -> str:
    return f"[{_EQUIV[ch]}]" if ch in _EQUIV else re.escape(ch)


def _significant(value: str) -> str:
    """The value's meaningful characters — whitespace, tatweel and harakat removed."""
    return _NOISE.sub("", value)


def _flex_pattern(value: str) -> re.Pattern:
    """Variant-tolerant regex for `value`, ignoring internal whitespace/diacritics."""
    chars = [_char_class(ch) for ch in _significant(value)]
    return re.compile(_BETWEEN.join(chars) if chars else re.escape(value))


def _variants(value: str) -> Iterable[str]:
    """The value, the honorific-stripped form, and the reversed word order.

    Reversed order matters because the model sometimes flags a name in a different
    order than the text writes it ("الغريب محمد" vs "محمد الغريب") — both must redact.
    """
    yield value
    toks = value.split()
    core = toks[1:] if (len(toks) > 1 and toks[0] in HONORIFICS) else toks
    if len(toks) > 1 and toks[0] in HONORIFICS:
        yield " ".join(core)
    if len(core) > 1:
        yield " ".join(reversed(core))


# Structured PII that the model may miss — always removed deterministically.
_STRUCTURED = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),      # email
    re.compile(r"(?:\+212|00212|0)\s?[5-7](?:[\s.\-]?\d){8}"),          # Moroccan phone
    re.compile(r"\b[A-Za-z]{1,2}\s?\d{5,6}\b"),                          # CIN / CNIE
    re.compile(r"\b[A-Z]{2}\d{2}(?:\s?\d){16,24}\b"),                    # IBAN
]


def redact_structured(text: str, token: str) -> tuple[str, int]:
    """Remove structured identifiers (email/phone/national-ID/IBAN) by pattern."""
    hits = 0
    for rx in _STRUCTURED:
        text, n = rx.subn(token, text)
        hits += n
    return text, hits


def redact_text(text: str, entities: List[PIIEntity], token: str) -> tuple[str, RedactionReport]:
    report = RedactionReport()

    # Deduplicate, longest first, so longer values are redacted before any
    # shorter substring of them.
    values = sorted({e.text for e in entities if e.text.strip()}, key=len, reverse=True)

    for value in values:
        # Guard against catastrophic over-redaction: a 1–2 char "value" (a stray letter
        # or OCR fragment) would match all over the text and shred the document. A real
        # identifier is longer; skip anything shorter than 3 significant characters.
        if len(_significant(value)) < MIN_REDACTABLE_CHARS:
            report.unmatched.append(value)
            continue
        matched = False
        # Apply EVERY variant (not just the first that hits): the same person may be
        # written both "محمد الغريب" and "الغريب محمد" in one document, so redacting the
        # forward order must not stop us redacting the reversed one.
        for variant in _variants(value):
            if not variant.strip():
                continue
            text, n = _flex_pattern(variant).subn(token, text)
            if n:
                report.total_hits += n
                matched = True
        (report.replaced if matched else report.unmatched).append(value)

    return text, report
