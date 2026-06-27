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

    # processing
    pages_per_batch: int
    max_workers: int
    replacement_token: str

    # cost reporting (USD per 1M tokens)
    input_price_per_m: float
    output_price_per_m: float

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
            pages_per_batch=int(_get("PAGES_PER_BATCH", "5")),
            max_workers=int(_get("MAX_WORKERS", "4")),
            replacement_token=_get("REPLACEMENT_TOKEN", "XXXXXXX"),
            input_price_per_m=float(_get("INPUT_PRICE_PER_M", "0.10")),
            output_price_per_m=float(_get("OUTPUT_PRICE_PER_M", "0.40")),
            log_level=_get("LOG_LEVEL", "INFO").upper(),
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_price_per_m
            + output_tokens / 1_000_000 * self.output_price_per_m
        )
