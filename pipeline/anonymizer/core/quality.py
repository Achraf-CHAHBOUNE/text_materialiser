"""OCR quality check, shared by the provider (retry) and the pipeline (quarantine).

A scan that the model failed to read comes back either almost empty, or as a wall of
Arabic *presentation forms* / stray digits rather than normal Arabic letters. Both are
failures, and — measured on real files — usually transient: the same PDF transcribes
cleanly on a second attempt. So the provider retries on this signal, and the pipeline
only quarantines when retries are exhausted.
"""
from __future__ import annotations


def ocr_garbled(text: str) -> bool:
    """True when `text` is unreadable Arabic.

    Three real failure shapes seen in this corpus:
      - Arabic presentation forms (U+FB50-FEFF): glyphs instead of letters
      - Private Use Area (U+E000-F8FF) and Latin Extended-B (U+0180-024F): what a
        PDF text layer with a broken font encoding decodes to (e.g. "ǱƢǬǷ ǒǬǼǳƢƥ")
      - almost no Arabic at all
    """
    pres = arab = 0
    for c in text:
        o = ord(c)
        if (0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF   # presentation forms
                or 0xE000 <= o <= 0xF8FF                      # private use area
                or 0x0180 <= o <= 0x024F):                    # Latin Extended-B
            pres += 1
        elif 0x0600 <= o <= 0x06FF:                           # normal Arabic
            arab += 1
    n = len(text.strip())
    if n < 200:                       # too little text to judge
        return False
    arabic = pres + arab
    pres_ratio = pres / max(1, arabic)          # scan read as broken glyphs
    arabic_density = arabic / n                  # a real ruling is mostly Arabic
    return pres_ratio > 0.15 or arabic_density < 0.15


def text_layer_unreliable(text: str) -> bool:
    """Stricter than ocr_garbled — decides whether a PDF's text layer can be TRUSTED.

    Some rulings use a broken font for the header and a good one for the body, so only
    a small share of characters decode to glyphs — but that share is exactly the
    decision number and date we need to extract. ocr_garbled's 15% threshold lets those
    through; for routing, any real contamination means: ignore the text layer and let
    the vision model read the page images instead.
    """
    bad = arab = 0
    for c in text:
        o = ord(c)
        if (0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF
                or 0xE000 <= o <= 0xF8FF or 0x0180 <= o <= 0x024F):
            bad += 1
        elif 0x0600 <= o <= 0x06FF:
            arab += 1
    n = len(text.strip())
    if n < 200:
        return False
    return (bad / max(1, bad + arab)) > 0.03 or ((bad + arab) / n) < 0.15
