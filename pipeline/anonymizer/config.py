"""Configuration loaded from environment / .env file.

All tunables live here so the rest of the code never reads os.environ directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above this package) if present.
load_dotenv()


def _get(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _autodetect_soffice() -> str:
    # Imported lazily to keep config dependency-light.
    from .documents.convert import autodetect_soffice

    return autodetect_soffice()


@dataclass(frozen=True)
class Settings:
    # provider / model
    provider: str
    api_key: str
    model: str

    # paths
    input_dir: Path
    output_dir: Path
    state_file: Path
    db_path: Path        # SQLite case-linkage DB (kept in its own folder)

    # processing
    pages_per_batch: int
    max_workers: int
    replacement_token: str
    soffice_path: str   # LibreOffice binary for legacy .doc conversion ("" if none)

    # cost reporting (USD per 1M tokens)
    input_price_per_m: float
    output_price_per_m: float
    cached_price_per_m: float   # cache-read rate (Gemini 2.5 Flash-Lite: $0.01/1M)
    budget_usd: float    # hard ceiling; run halts when reached (0 = no limit)

    # prompt caching: cache the static instruction so its input tokens aren't re-billed
    cache_prompt: bool
    cache_ttl_seconds: int

    # verification: independent second pass re-checks the anonymized text for missed names
    verify_pass: bool

    # logging
    log_level: str

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            provider=_get("PROVIDER", "gemini").lower(),
            api_key=_get("GEMINI_API_KEY", ""),
            model=_get("MODEL", "gemini-2.5-flash-lite"),
            input_dir=Path(_get("INPUT_DIR", "input")),
            output_dir=Path(_get("OUTPUT_DIR", "output")),
            state_file=Path(_get("STATE_FILE", ".anonymizer_state.json")),
            db_path=Path(_get("DB_PATH", "data/cases.db")),
            pages_per_batch=int(_get("PAGES_PER_BATCH", "5")),
            max_workers=int(_get("MAX_WORKERS", "4")),
            replacement_token=_get("REPLACEMENT_TOKEN", "XXXXXXX"),
            soffice_path=_get("SOFFICE_PATH", "") or _autodetect_soffice(),
            input_price_per_m=float(_get("INPUT_PRICE_PER_M", "0.10")),
            output_price_per_m=float(_get("OUTPUT_PRICE_PER_M", "0.40")),
            cached_price_per_m=float(_get("CACHED_PRICE_PER_M", "0.01")),
            budget_usd=float(_get("BUDGET_USD", "0")),
            cache_prompt=_get("ENABLE_PROMPT_CACHE", "1") not in ("0", "false", "False", "no"),
            cache_ttl_seconds=int(_get("CACHE_TTL_SECONDS", "3600")),
            verify_pass=_get("ENABLE_VERIFY", "0") not in ("0", "false", "False", "no"),
            log_level=_get("LOG_LEVEL", "INFO").upper(),
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        # prompt_token_count includes cached tokens; cached input bills at the cache-read rate.
        billable_input = max(0, input_tokens - cached_tokens)
        return (
            billable_input / 1_000_000 * self.input_price_per_m
            + cached_tokens / 1_000_000 * self.cached_price_per_m
            + output_tokens / 1_000_000 * self.output_price_per_m
        )
