"""French translation of a ruling's text, on demand.

The platform holds no AI engine of its own (see README, "The boundary"): this is the
one exception, and a narrow one. It sends text that is *already anonymized* -- the
same text any signed-in reader can see on the page -- to Google's Gemini API, and
never a file, never an original document, never anything the leak gate has not passed.

A ruling is translated once. The result is stored and served from the database
afterwards, so the second reader pays nothing and waits for nothing.

Settings:
    TRANSLATE_API_KEY   the Gemini API key (falls back to GEMINI_API_KEY)
    TRANSLATE_MODEL     default gemini-2.5-flash-lite, the pipeline's model
    TRANSLATE_MAX_CHARS largest ruling we will translate (default 120,000)
"""
from __future__ import annotations

import os
import re
from typing import Callable, List

ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent")

# Long rulings go up in pieces: one request per ~6,000 characters, split on blank
# lines so a sentence is never cut in half. Arabic legal text runs about 1.4 tokens
# per character, so a piece this size leaves ample room for the French answer.
CHUNK_CHARS = 6000

PROMPT = (
    "Translate this Moroccan court ruling from Arabic into French.\n"
    "Rules:\n"
    "- Translate faithfully, in the register of French legal writing. Do not "
    "summarise, explain, or add anything.\n"
    "- Keep the layout: one line in, one line out, same paragraph breaks.\n"
    "- Leave XXXXXXX exactly as it is. It marks a name that was removed.\n"
    "- Keep numbers, dates and article references as written.\n"
    "- Use the accepted French names of Moroccan courts and chambers "
    "(محكمة النقض = Cour de cassation).\n"
    "- Answer with the translation alone.\n\n"
    "---\n"
)


class TranslationError(RuntimeError):
    """The translation could not be produced; the message says why."""


def split_for_translation(text: str, limit: int = CHUNK_CHARS) -> List[str]:
    """Cut the text into pieces at paragraph breaks, each under `limit`."""
    if len(text) <= limit:
        return [text] if text.strip() else []
    pieces, current = [], ""
    for para in re.split(r"(\n\s*\n)", text):
        if len(current) + len(para) > limit and current.strip():
            pieces.append(current)
            current = ""
        # A single paragraph longer than the limit is cut on line breaks instead.
        while len(para) > limit:
            cut = para.rfind("\n", 0, limit) + 1 or limit
            pieces.append(para[:cut])
            para = para[cut:]
        current += para
    if current.strip():
        pieces.append(current)
    return pieces


def _call_gemini(text: str, *, api_key: str, model: str, timeout: float) -> str:
    import httpx

    body = {
        "contents": [{"parts": [{"text": PROMPT + text}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 65535},
    }
    try:
        r = httpx.post(ENDPOINT.format(model=model), params={"key": api_key},
                       json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise TranslationError(f"could not reach the translation service: {e}") from e
    if r.status_code == 429:
        raise TranslationError("the translation service is busy; try again in a minute")
    if r.status_code >= 400:
        raise TranslationError(f"translation service refused the request ({r.status_code})")

    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        blocked = (data.get("promptFeedback") or {}).get("blockReason")
        raise TranslationError(f"no translation came back{f' ({blocked})' if blocked else ''}")
    first = candidates[0]
    parts = (first.get("content") or {}).get("parts") or []
    out = "".join(p.get("text", "") for p in parts).strip()
    if not out:
        raise TranslationError("the translation came back empty")
    if first.get("finishReason") == "MAX_TOKENS":
        raise TranslationError("the ruling is too long to translate in one piece")
    return out


def translate(text: str, *, api_key: str = "", model: str = "", timeout: float = 120.0,
              call: Callable[..., str] | None = None) -> str:
    """The text in French. Raises TranslationError, never a half translation."""
    text = (text or "").strip()
    if not text:
        raise TranslationError("this ruling has no text to translate")
    ceiling = int(os.getenv("TRANSLATE_MAX_CHARS", "120000"))
    if len(text) > ceiling:
        raise TranslationError(f"this ruling is too long to translate ({len(text):,} characters)")

    api_key = api_key or os.getenv("TRANSLATE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    model = model or os.getenv("TRANSLATE_MODEL", "gemini-2.5-flash-lite")
    if not api_key and call is None:
        raise TranslationError("translation is not configured on this server")

    send = call or (lambda piece: _call_gemini(piece, api_key=api_key, model=model,
                                               timeout=timeout))
    pieces = split_for_translation(text)
    return "\n\n".join(send(piece) for piece in pieces).strip()
