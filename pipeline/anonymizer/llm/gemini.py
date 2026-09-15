"""Gemini provider: native PDF OCR + PII detection in one call.

Uses google-genai. PDF batches are small (a few pages), so we send bytes inline.
Structured JSON is requested via response_mime_type; parsing is defensive.
"""
from __future__ import annotations

import json
import re
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

    # Gemini 2.x on Vertex has no fixed per-project cap: capacity is shared, and at
    # busy moments it answers 429 "Resource exhausted, try again later". Four tries
    # over ~14 seconds gave up too soon -- 24 rulings in one 32-worker run failed that
    # way and had to be rerun. Six tries backing off to a minute ride it out.
    @retry(
        reraise=True,
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=2, min=2, max=60),
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
    MIN_CHARS_PER_PAGE = 120        # a single page below this came back empty
    COMPLETE_CHARS_PER_PAGE = 400   # a multi-page batch below this stopped early

    def process_pdf(self, pdf_bytes: bytes, page_count: int = 1) -> BatchResult:
        """OCR a scanned page-batch, retrying when the transcription comes back thin.

        The model intermittently answers with little or no transcription even though
        the scan is readable -- sometimes nothing, sometimes only the last page. That
        is a transient failure, not a bad document, and tenacity only retries
        *exceptions*, so the content itself is checked: a multi-page batch must
        average COMPLETE_CHARS_PER_PAGE (real rulings never fell below ~670 per page
        across 3,174 outputs; the partial ones sat at 61-336). If every attempt is
        thin, a multi-page batch is split, since a single page is read most reliably.
        The best attempt is kept, and every attempt's tokens are counted -- the
        discarded ones were paid for too.
        """
        from google.genai import types

        cap = max(4000, self.MAX_OUTPUT_PER_PAGE * max(1, page_count))
        part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        # One page may legitimately be short (a closing page of signatures), so the
        # stricter per-page average applies only to multi-page batches.
        per_page = self.COMPLETE_CHARS_PER_PAGE if page_count > 1 else self.MIN_CHARS_PER_PAGE
        floor = per_page * max(1, page_count)
        best: BatchResult | None = None
        spent = [0, 0, 0]
        last = self.OCR_ATTEMPTS - 1
        for attempt in range(self.OCR_ATTEMPTS):
            resp = self._generate([part], OCR_PII_PROMPT, "ocr", max_output=cap)
            usage = getattr(resp, "usage_metadata", None)
            spent[0] += getattr(usage, "prompt_token_count", 0) or 0
            spent[1] += getattr(usage, "candidates_token_count", 0) or 0
            spent[2] += getattr(usage, "cached_content_token_count", 0) or 0
            try:
                result = self._to_result(resp, include_pages=True)
            except TruncatedResponse:
                # A dense page can genuinely need more room than the per-page ceiling
                # allows. Give it more and try again rather than losing the document;
                # the ceiling still exists to stop a runaway on a garbled scan.
                if attempt < last:
                    cap = min(cap * 2, self.MAX_OUTPUT_CEILING)
                    continue
                # Still cut off at the API's own maximum: no budget fits this batch.
                if page_count > 1:
                    return _add_spent(self._split_and_process(pdf_bytes, page_count), spent)
                if best is None:
                    raise
                break
            except UnparseableResponse:
                # A malformed reply is worth another attempt; give up only if no
                # attempt produced anything usable.
                if attempt == last and best is None:
                    raise
                continue
            text = "".join(result.pages).strip()
            if len(text) >= floor and not ocr_garbled(text):
                return _with_spent(result, spent)
            if best is None or _chars(result) > _chars(best):
                best = result
        if page_count > 1:
            split = self._split_and_process(pdf_bytes, page_count)
            if best is None or _chars(split) > _chars(best):
                return _add_spent(split, spent)
        return _with_spent(best, spent)

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
            merged = _merge_results(merged, self.process_pdf(buf.getvalue(), hi - lo))
        return merged

    # Below this many characters a text batch is not split further.
    MIN_SPLIT_CHARS = 1500

    def process_text(self, text: str) -> BatchResult:
        # Text is already extracted locally; the model only detects PII + classifies.
        resp = self._generate([text], PII_TEXT_PROMPT, "text")
        try:
            try:
                return self._to_result(resp, include_pages=False)
            except UnparseableResponse:
                # An empty or unreadable reply is usually transient; the scanned-PDF
                # path already retried it, the text path failed the ruling outright.
                resp = self._generate([text], PII_TEXT_PROMPT, "text")
                return self._to_result(resp, include_pages=False)
        except TruncatedResponse:
            # The reply would not fit: halve the text and detect in each half. The
            # scanned-PDF path already did this; without it here, a dense text batch
            # was simply lost. Halves recurse; a piece too small to split fails.
            if len(text) < self.MIN_SPLIT_CHARS:
                raise
            first, second = _split_text(text)
            return _merge_results(self.process_text(first), self.process_text(second))

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
        pages = ["" if p is None else str(p) for p in (data.get("pages") or [])] if include_pages else []
        pii = [
            PIIEntity(text=_s(e.get("text", "")), type=_s(e.get("type", "other")))
            for e in data.get("pii", [])
            if _s(e.get("text", ""))
        ]

        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0
        cached_tok = getattr(usage, "cached_content_token_count", 0) or 0

        own = data.get("own") or {}
        identity = DocIdentity(
            level=_s(data.get("level", "")),
            court=_s(own.get("court", "")),
            city=_s(own.get("city", "")),
            decision_no=_s(own.get("decision_no", "")),
            date=_s(own.get("date", "")),
            file_no=_s(own.get("file_no", "")),
            outcome=_s(own.get("outcome", "")),
        )
        refs = [
            DocRef(
                court=_s(r.get("court", "")),
                city=_s(r.get("city", "")),
                decision_no=_s(r.get("decision_no", "")),
                date=_s(r.get("date", "")),
                file_no=_s(r.get("file_no", "")),
            )
            for r in (data.get("refs") or [])
            if any(_s(r.get(k, "")) for k in ("decision_no", "file_no"))
        ]

        return BatchResult(
            pages=pages,
            pii=pii,
            court=_s(data.get("court", "")),
            category=_s(data.get("category", "")),
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


def _s(value) -> str:
    """A model field as clean text. JSON null is empty -- not the string "None",
    which had reached stored decision numbers and dates as a literal value."""
    return "" if value is None else str(value).strip()


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
    # Stray quotes inside the transcription (see _repair_stray_quotes).
    start, end = text.find("{"), text.rfind("}")
    for candidate in dict.fromkeys([text] + ([text[start:end + 1]] if end > start >= 0 else [])):
        repaired = _repair_stray_quotes(candidate)
        if repaired is not None:
            data = _coerce(repaired)
            _require_every_entry(candidate, data)
            return data
    raise UnparseableResponse("no JSON object found in response")


# JSON errors that mean "a string ended early": the parser finished a value and
# then met ordinary text where a delimiter belonged.
_EARLY_END = ("Expecting ',' delimiter", "Expecting ':' delimiter", "Expecting property name")
_MAX_QUOTE_REPAIRS = 200
_ENTRY = re.compile(r'"text"\s*:')


def _last_unescaped_quote(text: str, before: int) -> int:
    i = text.rfind('"', 0, before)
    while i > 0:
        slashes = len(text[:i]) - len(text[:i].rstrip("\\"))
        if slashes % 2 == 0:
            return i
        i = text.rfind('"', 0, i)
    return i


def _repair_stray_quotes(text: str):
    """Parse JSON whose strings contain unescaped quotation marks, or return None.

    Transcribing a ruling that quotes the law, the model escapes the opening quote
    and not the closing one: \\"أنه طبقا لمقتضيات الفصل 1241 من ق. ل.ع"، ... The
    stray quote ends the string early and the reply is invalid JSON. At temperature
    0 every retry returns the same reply, so 32 rulings could never be processed --
    and before replies were checked, the old fallback read them as "no pages, no
    names" and delivered 63 empty files as clean.

    Each time the parser meets text where a delimiter belonged, the last unescaped
    quote before that point is the one that ended the string early; escape it and
    parse again.
    """
    for _ in range(_MAX_QUOTE_REPAIRS):
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError as e:
            if e.msg.startswith("Invalid \\escape"):
                # A backslash JSON does not allow ("\iota" -- the model misread part
                # of a scan as LaTeX). Doubling it keeps it as literal text and cannot
                # change the reply's structure.
                text = text[:e.pos] + "\\" + text[e.pos:]
                continue
            if not e.msg.startswith(_EARLY_END):
                return None
            q = _last_unescaped_quote(text, e.pos)
            if q <= 0:
                return None
            text = text[:q] + "\\" + text[q:]
    return None


def _require_every_entry(raw: str, data: dict) -> None:
    """Reject a repair that lost any name entry the raw reply contained.

    A wrong repair can fold the "pii" list into a page's text and still parse. The
    document would then be redacted for fewer names than the model found, and the
    leak gate would not notice, because it only re-scans the names it is handed.
    """
    found = len(_ENTRY.findall(raw))
    kept = len(data.get("pii") or []) if isinstance(data, dict) else 0
    if found and kept < found:
        raise UnparseableResponse(f"quote repair kept {kept} of {found} name entries")


def _split_text(text: str) -> tuple[str, str]:
    """Two halves of `text`, cut at the line break nearest the middle."""
    mid = len(text) // 2
    cut = text.rfind("\n", 0, mid)
    if cut < len(text) // 4:
        cut = text.find("\n", mid)
    if cut <= 0:
        cut = mid
    return text[:cut], text[cut:]


def _merge_results(a: BatchResult, b: BatchResult) -> BatchResult:
    """One BatchResult covering both halves: lists joined, first non-empty scalar."""
    return BatchResult(
        pages=a.pages + b.pages,
        pii=a.pii + b.pii,
        court=a.court or b.court,
        category=a.category or b.category,
        identity=a.identity or b.identity,
        refs=a.refs + b.refs,
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cached_tokens=a.cached_tokens + b.cached_tokens,
    )


def _chars(result: BatchResult) -> int:
    return len("".join(result.pages).strip())


def _with_spent(result: BatchResult, spent: list) -> BatchResult:
    """`result` with its tokens replaced by the total over every attempt."""
    result.input_tokens, result.output_tokens, result.cached_tokens = spent
    return result


def _add_spent(result: BatchResult, spent: list) -> BatchResult:
    """`result` (already counting its own calls) plus the attempts made before it."""
    result.input_tokens += spent[0]
    result.output_tokens += spent[1]
    result.cached_tokens += spent[2]
    return result
