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

from .base import BatchResult, DocumentAI, PIIEntity
from .prompt import OCR_PII_PROMPT, PII_TEXT_PROMPT


class GeminiProvider(DocumentAI):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set (see .env).")
        # Imported here so the package imports even when google-genai isn't installed.
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(Exception),
    )
    def _generate(self, contents: list) -> Any:
        from google.genai import types

        return self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )

    def process_pdf(self, pdf_bytes: bytes) -> BatchResult:
        from google.genai import types

        resp = self._generate([
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            OCR_PII_PROMPT,
        ])
        return self._to_result(resp, include_pages=True)

    def process_text(self, text: str) -> BatchResult:
        # Text is already extracted locally; the model only detects PII + classifies.
        resp = self._generate([PII_TEXT_PROMPT + text])
        return self._to_result(resp, include_pages=False)

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

        return BatchResult(
            pages=pages,
            pii=pii,
            court=str(data.get("court", "")).strip(),
            category=str(data.get("category", "")).strip(),
            input_tokens=in_tok,
            output_tokens=out_tok,
        )


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
