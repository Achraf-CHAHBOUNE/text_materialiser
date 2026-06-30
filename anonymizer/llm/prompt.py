"""Instruction prompts sent to the provider.

Two modes share the same PII + classification rules:
- OCR_PII_PROMPT  : scanned PDFs (model must OCR, then detect + classify).
- PII_TEXT_PROMPT : text already extracted locally (.docx / text PDFs) -> detect + classify only.

The chamber taxonomy is injected from anonymizer.core.categories so it lives in one place.
"""

from ..core.categories import CATEGORIES, TAXONOMY, UNKNOWN

_TAXONOMY_LINES = "\n".join(f"  - {court} / {chamber}" for court, chamber in TAXONOMY)
_ALLOWED_CHAMBERS = "، ".join(CATEGORIES)

# --- shared rule fragments --------------------------------------------------

_PII_RULES = """List every value that could identify an INDIVIDUAL. Copy each value VERBATIM, \
character for character and with the same spacing as in the text, so it can be matched and \
replaced by exact string search.
Detect:
- First name, last name, full name (people, including lawyers/الأساتذة المحامين)
- Personal/home addresses
- National ID (CIN / CNIE), passport numbers
- Phone, fax, email
- Dates of birth
- Any other detail identifying an individual

IMPORTANT for names: capture the person's COMPLETE name as one value — include ALL given \
names, surnames and name particles that belong to it (e.g. write "إدريس لحلو أمين", not \
just "إدريس لحلو"). Do not split one person's name into several entries and do not drop a \
trailing part of the name.

Do NOT flag: names of companies/banks, government bodies, courts, ministries, case/file \
numbers, decision numbers, or generic legal terms — unless they directly identify a specific \
individual."""

_CLASSIFY_RULES = f"""Identify which court and chamber issued/handles this document, choosing \
from this list:
{_TAXONOMY_LINES}
Return "court" (the part before " / ") and "category" (the CHAMBER, EXACTLY one of: \
{_ALLOWED_CHAMBERS}). If undeterminable, use "{UNKNOWN}" for both."""

# --- mode 1: scanned PDF (OCR + detect + classify) --------------------------

OCR_PII_PROMPT = f"""You are an OCR, PII-detection and classification engine for scanned \
Arabic legal documents (e.g. Moroccan court rulings / محكمة النقض).

You receive a PDF of one or more scanned pages. Do THREE tasks and return ONLY JSON.

TASK 1 - OCR:
Transcribe the FULL text of EACH page exactly as it appears. Preserve right-to-left Arabic \
reading order and line breaks (use "\\n"). Do NOT translate, summarize, fix or reformat. \
Keep all numbers, punctuation and spelling exactly as-is.

TASK 2 - PII DETECTION (natural persons only):
{_PII_RULES}

TASK 3 - CLASSIFICATION:
{_CLASSIFY_RULES}

Return ONLY this JSON (no markdown fences, no commentary):
{{
  "pages": ["<full OCR text of page 1>", "<full OCR text of page 2>"],
  "pii": [
    {{"text": "<verbatim value>", "type": "name|address|national_id|passport|phone|email|dob|other"}}
  ],
  "court": "<court name or {UNKNOWN}>",
  "category": "<chamber name or {UNKNOWN}>"
}}
The "pages" array MUST have exactly one entry per page, in order.
"""

# --- mode 2: already-extracted text (.docx / text PDF) ----------------------

PII_TEXT_PROMPT = f"""You are a PII-detection and classification engine for Arabic legal \
documents (e.g. Moroccan court rulings / محكمة النقض).

You receive the plain TEXT of a document (already extracted — do NOT transcribe or echo it). \
Do TWO tasks and return ONLY JSON.

TASK 1 - PII DETECTION (natural persons only):
{_PII_RULES}

TASK 2 - CLASSIFICATION:
{_CLASSIFY_RULES}

Return ONLY this JSON (no markdown fences, no commentary):
{{
  "pii": [
    {{"text": "<verbatim value>", "type": "name|address|national_id|passport|phone|email|dob|other"}}
  ],
  "court": "<court name or {UNKNOWN}>",
  "category": "<chamber name or {UNKNOWN}>"
}}

--- DOCUMENT TEXT ---
"""
