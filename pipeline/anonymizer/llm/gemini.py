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

    def process_pdf(self, pdf_bytes: bytes) -> BatchResult:
        from google.genai import types

        resp = self._generate(
            [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")],
            OCR_PII_PROMPT, "ocr")
        return self._to_result(resp, include_pages=True)

    def process_text(self, text: str) -> BatchResult:
        # Text is already extracted locally; the model only detects PII + classifies.
        resp = self._generate([text], PII_TEXT_PROMPT, "text")
        return self._to_result(resp, include_pages=False)

    def verify_pii(self, anonymized_text: str, token: str) -> tuple[list[str], int, int]:
        # Independent second look: cheap (text in, tiny name-list out).
        from .prompt import VERIFY_PROMPT
        resp = self._generate([anonymized_text], VERIFY_PROMPT.replace("{TOKEN}", token),
                              "verify", max_output=256)
        data = _parse_json(resp.text or "")
        # Drop the token, and drop institutions the verifier wrongly reports as "names"
        # (the State, ministries, companies, courts…) — the brief keeps those.
        names = [n for n in (str(x).strip() for x in data.get("remaining", []))
                 if n and token not in n and n != token and not _is_entity(n)]
        usage = getattr(resp, "usage_metadata", None)
        return (names,
                getattr(usage, "prompt_token_count", 0) or 0,
                getattr(usage, "candidates_token_count", 0) or 0)

    def _to_result(self, resp: Any, include_pages: bool) -> BatchResult:
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


def _parse_json(text: str) -> dict:
    """Parse model JSON, tolerating ```json fences or stray text around it."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"pages": [], "pii": []}
