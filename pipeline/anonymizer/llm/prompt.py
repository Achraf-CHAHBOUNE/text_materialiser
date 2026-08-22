"""Instruction prompts sent to the provider.

Two modes share the same PII + classification + case-identification rules:
- OCR_PII_PROMPT  : scanned PDFs (model must OCR, then detect + classify + identify).
- PII_TEXT_PROMPT : text already extracted locally (.doc/.docx / text PDFs).

The chamber taxonomy is injected from anonymizer.core.categories so it lives in one place.
"""

from ..core.categories import CATEGORIES, COURTS, UNKNOWN

_COURT_LINES = "\n".join(f"  - {court}" for court in COURTS)
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
trailing part of the name. Do NOT include courtesy titles in the value (السيد، السيدة، \
الأستاذ، المستشار، الدكتور…) — return only the actual name.

Do NOT flag: names of companies/banks, government bodies, courts, ministries, case/file \
numbers, decision numbers, or generic legal terms — unless they directly identify a specific \
individual."""

_CLASSIFY_RULES = f"""Identify which court issued/handles this document, and its chamber.
- "court": the issuing court (blue header), typically one of:
{_COURT_LINES}
- "category": the CHAMBER, EXACTLY one short label from: {_ALLOWED_CHAMBERS}.
If undeterminable, use "{UNKNOWN}"."""

_IDENTITY_RULES = """Extract the document's OWN case identity and every LOWER decision it \
reviews/cites, so cases can be linked across court levels. Copy all numbers/dates VERBATIM.
- "level": court level of THIS document — "ابتدائي" (المحكمة الابتدائية/الإدارية/التجارية as \
first instance), "استئناف" (محاكم الاستئناف), or "نقض" (محكمة النقض).
- "own": {"court","city","decision_no" (رقم القرار/الحكم),"date","file_no" (رقم/عدد الملف — \
often in the header),"outcome" (منطوق: تأييد/إلغاء/تعديل or نقض/رفض/إحالة …)}.
- "refs": array of the LOWER decisions this document reviews or cites (the appealed/cassated \
decision), each {"court","city","decision_no","date","file_no"}. Include ALL of them."""

_IDENTITY_JSON = """"level": "ابتدائي|استئناف|نقض|غير محدد",
  "own": {"court": "", "city": "", "decision_no": "", "date": "", "file_no": "", "outcome": ""},
  "refs": [ {"court": "", "city": "", "decision_no": "", "date": "", "file_no": ""} ]"""

# --- mode 1: scanned PDF (OCR + detect + classify + identify) ---------------

OCR_PII_PROMPT = f"""You are an OCR, PII-detection, classification and case-identification \
engine for scanned Arabic legal documents (Moroccan court rulings / محكمة النقض).

You receive a PDF of one or more scanned pages. Do the tasks and return ONLY JSON.

TASK 1 - OCR:
Transcribe the FULL text of EACH page exactly as it appears. Preserve right-to-left Arabic \
reading order and line breaks (use "\\n"). Do NOT translate, summarize, fix or reformat.

TASK 2 - PII DETECTION (natural persons only):
{_PII_RULES}

TASK 3 - CLASSIFICATION:
{_CLASSIFY_RULES}

TASK 4 - CASE IDENTIFICATION:
{_IDENTITY_RULES}

Return ONLY this JSON (no markdown fences, no commentary):
{{
  "pages": ["<full OCR text of page 1>", "<full OCR text of page 2>"],
  "pii": [ {{"text": "<verbatim value>", "type": "name|address|national_id|passport|phone|email|dob|other"}} ],
  "court": "<court name or {UNKNOWN}>",
  "category": "<chamber name or {UNKNOWN}>",
  {_IDENTITY_JSON}
}}
The "pages" array MUST have exactly one entry per page, in order."""

# --- mode 2: already-extracted text (.doc/.docx / text PDF) -----------------

PII_TEXT_PROMPT = f"""You are a PII-detection, classification and case-identification engine \
for Arabic legal documents (Moroccan court rulings / محكمة النقض).

You receive the plain TEXT of a document (already extracted — do NOT transcribe or echo it). \
Do the tasks and return ONLY JSON.

TASK 1 - PII DETECTION (natural persons only):
{_PII_RULES}

TASK 2 - CLASSIFICATION:
{_CLASSIFY_RULES}

TASK 3 - CASE IDENTIFICATION:
{_IDENTITY_RULES}

Return ONLY this JSON (no markdown fences, no commentary):
{{
  "pii": [ {{"text": "<verbatim value>", "type": "name|address|national_id|passport|phone|email|dob|other"}} ],
  "court": "<court name or {UNKNOWN}>",
  "category": "<chamber name or {UNKNOWN}>",
  {_IDENTITY_JSON}
}}

The document text to analyse is provided as the user message."""


# --- verification pass: independently re-check an ALREADY-anonymized text -----

VERIFY_PROMPT = f"""You are auditing an ALREADY-anonymized Moroccan court ruling. Personal \
names of individuals have been replaced with the token "{{TOKEN}}". Your ONLY job is to find \
personal names of NATURAL PERSONS that are STILL PRESENT (missed by the anonymization).

Return a name only if it identifies a specific individual (a party, lawyer/الأستاذ, expert, \
witness, judge). Copy each remaining name VERBATIM as it appears in the text.
Do NOT return: the token "{{TOKEN}}", companies/banks, government bodies, courts, ministries, \
cities, case/file/decision numbers, dates, or generic legal terms.

Return ONLY this JSON (no markdown, no commentary):
{{{{ "remaining": ["<name still present>", ...] }}}}
An empty array means the text is clean.

The anonymized text is provided as the user message."""
