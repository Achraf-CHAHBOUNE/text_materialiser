"""Gemini provider: native PDF OCR + PII detection in one call.

Uses google-genai. PDF batches are small (a few pages), so we send bytes inline.
Structured JSON is requested via response_mime_type; parsing is defensive.
"""
from __future__ import annotations

import json
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..core.quality import ocr_garbled
from .base import BatchResult, DocIdentity, DocRef, DocumentAI, PIIEntity
from .prompt import OCR_PII_PROMPT, PII_TEXT_PROMPT


class GeminiProvider(DocumentAI):
    def __init__(self, api_key: str, model: str, cache_prompt: bool = True, cache_ttl: int = 3600):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set (see .env).")
        # Imported here so the package imports even when google-genai isn't installed.
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._cache_prompt = cache_prompt
        self._cache_ttl = cache_ttl
        self._caches: dict[str, str | None] = {}   # key -> cached-content name, or None if not cached

    def _cache_name(self, key: str, prompt: str) -> str | None:
        """Get-or-create an explicit context cache for `prompt`. The instruction is
        identical for every document, so caching it once means its input tokens are
        billed at the reduced cached rate on every subsequent call. Returns None (and
        we fall back to an inline system_instruction) if the model/prompt can't be
        cached — e.g. the prompt is below the model's minimum cacheable size."""
        if not self._cache_prompt:
            return None
        if key not in self._caches:
            from google.genai import types
            try:
                cache = self._client.caches.create(
                    model=self._model,
                    config=types.CreateCachedContentConfig(
                        system_instruction=prompt,
                        ttl=f"{self._cache_ttl}s",
                        display_name=f"anon-{key}",
                    ),
                )
                self._caches[key] = cache.name
            except Exception:
                self._caches[key] = None   # too small / unsupported -> inline fallback
        return self._caches[key]

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(Exception),
    )
    def _generate(self, contents: list, prompt: str, key: str, max_output: int = 0) -> Any:
        from google.genai import types

        cache = self._cache_name(key, prompt)
        cfg: dict = {"response_mime_type": "application/json", "temperature": 0.0}
        if max_output:
            cfg["max_output_tokens"] = max_output
        if cache:                       # instruction lives in the cache
            cfg["cached_content"] = cache
        else:                           # not cached: send the instruction inline
            cfg["system_instruction"] = prompt
        return self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(**cfg),
        )

    # Generous per-page ceiling for OCR output. A real page transcribes to ~1-2k
    # tokens; a runaway on a garbled scan hit 16k per page (65k total), costing 10x
    # and stalls the batch for minutes. Cap it.
    MAX_OUTPUT_PER_PAGE = 6000
    # Absolute ceiling when retrying a truncated reply with a bigger budget.
    # The API accepts 1..65536 EXCLUSIVE, so 65536 itself is rejected outright.
    MAX_OUTPUT_CEILING = 65535
    # Retry an OCR call whose response comes back empty/degenerate (transient model
    # failure). Measured: all 4 "poor-OCR" quarantines in a 10-doc sample were these,
    # and every one transcribed cleanly on a second attempt.
    OCR_ATTEMPTS = 3
    MIN_CHARS_PER_PAGE = 120

    def process_pdf(self, pdf_bytes: bytes, page_count: int = 1) -> BatchResult:
        """OCR a scanned page-batch, retrying when the model returns an empty/degenerate
        response.

        The model intermittently answers with no (or almost no) transcription even
        though the scan is perfectly readable — a transient failure, not a bad
        document. tenacity only retries *exceptions*, so those responses used to sail
        through and get the document quarantined as "poor OCR". Retry on the content.
        """
        from google.genai import types

        cap = max(4000, self.MAX_OUTPUT_PER_PAGE * max(1, page_count))
        part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        # A genuine page yields hundreds of characters; anything below this is a failure.
        floor = self.MIN_CHARS_PER_PAGE * max(1, page_count)
        result = None
        for attempt in range(self.OCR_ATTEMPTS):
            resp = self._generate([part], OCR_PII_PROMPT, "ocr", max_output=cap)
            try:
                result = self._to_result(resp, include_pages=True)
            except TruncatedResponse:
                # A dense page can genuinely need more room than the per-page ceiling
                # allows. Give it more and try again rather than losing the document;
                # the ceiling still exists to stop a runaway on a garbled scan.
                if attempt == self.OCR_ATTEMPTS - 1:
                    # Still cut off at the API's own maximum: no budget will fit this
                    # batch, so halve it. A batch of one page that still overflows is
                    # genuinely unprocessable and is allowed to fail.
                    if page_count > 1:
                        return self._split_and_process(pdf_bytes, page_count)
                    raise
                cap = min(cap * 2, self.MAX_OUTPUT_CEILING)
                continue
            except UnparseableResponse:
                # A malformed reply is worth another attempt; only give up (and let
                # the document be quarantined) if the last one is malformed too.
                if attempt == self.OCR_ATTEMPTS - 1:
                    raise
                continue
            text = "".join(result.pages).strip()
            if len(text) >= floor and not ocr_garbled(text):
                return result
        return result

    def _split_and_process(self, pdf_bytes: bytes, page_count: int) -> BatchResult:
        """OCR a too-large batch as two halves and stitch the results back together.

        Reached only when even the maximum output budget cannot hold the reply for
        this many pages. Splitting keeps the document rather than losing it, and the
        halves recurse, so a batch that is still too big keeps halving down to
        single pages.
        """
        import io

        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        mid = page_count // 2
        merged = BatchResult()
        for lo, hi in ((0, mid), (mid, page_count)):
            writer = PdfWriter()
            for i in range(lo, hi):
                writer.add_page(reader.pages[i])
            buf = io.BytesIO()
            writer.write(buf)
            part = self.process_pdf(buf.getvalue(), hi - lo)
            merged.pages.extend(part.pages)
            merged.pii.extend(part.pii)
            merged.refs.extend(part.refs)
            merged.input_tokens += part.input_tokens
            merged.output_tokens += part.output_tokens
            merged.cached_tokens += part.cached_tokens
            merged.court = merged.court or part.court
            merged.category = merged.category or part.category
            merged.identity = merged.identity or part.identity
        return merged

    def process_text(self, text: str) -> BatchResult:
        # Text is already extracted locally; the model only detects PII + classifies.
        resp = self._generate([text], PII_TEXT_PROMPT, "text")
        return self._to_result(resp, include_pages=False)

    def verify_pii(self, anonymized_text: str, token: str) -> tuple[list[str], int, int]:
        # Independent second look: cheap (text in, tiny name-list out).
        from .prompt import VERIFY_PROMPT
        resp = self._generate([anonymized_text], VERIFY_PROMPT.replace("{TOKEN}", token),
                              "verify", max_output=256)
        try:
            data = _parse_json(resp.text or "")
        except UnparseableResponse:
            data = {}          # advisory pass only — never fail a document on it
        # Drop the token, and drop institutions the verifier wrongly reports as "names"
        # (the State, ministries, companies, courts…) — the brief keeps those.
        names = [n for n in (str(x).strip() for x in data.get("remaining", []))
                 if n and token not in n and n != token and not _is_entity(n)]
        usage = getattr(resp, "usage_metadata", None)
        return (names,
                getattr(usage, "prompt_token_count", 0) or 0,
                getattr(usage, "candidates_token_count", 0) or 0)

    @staticmethod
    def _check_complete(resp: Any) -> None:
        """Raise if the model stopped because it ran out of output budget."""
        for cand in (getattr(resp, "candidates", None) or []):
            if str(getattr(cand, "finish_reason", "") or "").upper().endswith("MAX_TOKENS"):
                raise TruncatedResponse("reply cut off at the output-token cap")

    def _to_result(self, resp: Any, include_pages: bool) -> BatchResult:
        self._check_complete(resp)
        data = _parse_json(resp.text or "")
        pages = [str(p) for p in data.get("pages", [])] if include_pages else []
        pii = [
            PIIEntity(text=str(e.get("text", "")), type=str(e.get("type", "other")))
            for e in data.get("pii", [])
            if str(e.get("text", "")).strip()
        ]

        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0
        cached_tok = getattr(usage, "cached_content_token_count", 0) or 0

        own = data.get("own") or {}
        identity = DocIdentity(
            level=str(data.get("level", "")).strip(),
            court=str(own.get("court", "")).strip(),
            city=str(own.get("city", "")).strip(),
            decision_no=str(own.get("decision_no", "")).strip(),
            date=str(own.get("date", "")).strip(),
            file_no=str(own.get("file_no", "")).strip(),
            outcome=str(own.get("outcome", "")).strip(),
        )
        refs = [
            DocRef(
                court=str(r.get("court", "")).strip(),
                city=str(r.get("city", "")).strip(),
                decision_no=str(r.get("decision_no", "")).strip(),
                date=str(r.get("date", "")).strip(),
                file_no=str(r.get("file_no", "")).strip(),
            )
            for r in (data.get("refs") or [])
            if any(str(r.get(k, "")).strip() for k in ("decision_no", "file_no"))
        ]

        return BatchResult(
            pages=pages,
            pii=pii,
            court=str(data.get("court", "")).strip(),
            category=str(data.get("category", "")).strip(),
            identity=identity,
            refs=refs,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
        )


# Institutional terms — a "name" containing any of these is an organisation, not a
# natural person, so the verifier must not flag it (the brief keeps courts/State/etc.).
_ENTITY_TERMS = (
    "الدولة", "المغربية", "الخزينة", "الوكيل القضائي", "شركة", "مؤسسة", "بنك", "وكالة",
    "صندوق", "وزارة", "وزير", "جماعة", "مجلس", "عمالة", "إقليم", "بلدية", "محافظة",
    "محكمة", "النيابة", "مندوبية", "ديوان", "مكتب", "قباضة", "إدارة", "مديرية", "تعاونية",
    "المكتب الوطني", "الوكالة", "الجماعة",
)


def _is_entity(name: str) -> bool:
    return any(term in name for term in _ENTITY_TERMS)


class TruncatedResponse(RuntimeError):
    """The model hit its output-token cap mid-reply, so the JSON is incomplete.

    Kept separate from an unreadable reply because the remedy differs: this one is
    retried with a larger budget. It must never be salvaged into partial data -- a
    half-written "pii" array looks perfectly valid, and redacting only the names that
    made it under the cap would ship the rest, with the leak gate none the wiser
    because it only re-scans the values it was given.
    """


class UnparseableResponse(RuntimeError):
    """The model's reply could not be read as the expected JSON object.

    Raised rather than defaulted, because the safe-looking default ("no PII
    found") is the dangerous one: it writes the document out with nothing
    redacted, and the leak gate then has no values to scan, so the file ships
    as clean. Failing here quarantines the document instead.
    """


def _coerce(data):
    """Normalise the shapes the model actually returns into the expected object."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        # One or more complete result objects in an array. A PDF holding two rulings
        # comes back as two objects, so they are MERGED rather than picked from:
        # taking only the first would silently drop the second ruling's PII and ship
        # those names unredacted. Checked before the bare-list case, since a result
        # object is itself a dict and would otherwise look like a malformed PII entry.
        wrapper = {"pii", "pages", "own", "refs", "level", "court", "category"}
        if data and all(isinstance(e, dict) and (wrapper & set(e)) for e in data):
            merged: dict = {"pages": [], "pii": [], "refs": []}
            for e in data:
                for key in ("pages", "pii", "refs"):
                    merged[key].extend(e.get(key) or [])
                for key in ("level", "court", "category", "own", "outcome"):
                    if not merged.get(key) and e.get(key):
                        merged[key] = e[key]
            return merged
        # A bare array: the model emitted the pii list and dropped the wrapper object.
        if all(isinstance(e, dict) for e in data) and any("text" in e for e in data):
            return {"pages": [], "pii": data}
        if not data:                      # an empty array carries no PII claim at all
            raise UnparseableResponse("model returned an empty array")
    raise UnparseableResponse(f"unexpected JSON type: {type(data).__name__}")


def _parse_json(text: str) -> dict:
    """Parse model JSON, tolerating ```json fences or stray text around it.

    Raises UnparseableResponse if nothing usable can be recovered.
    """
    text = text.strip()
    if not text:
        raise UnparseableResponse("empty response")
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return _coerce(json.loads(text))
    except json.JSONDecodeError:
        pass
    # Salvage the outermost object or array embedded in surrounding prose.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return _coerce(json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                continue
    raise UnparseableResponse("no JSON object found in response")
