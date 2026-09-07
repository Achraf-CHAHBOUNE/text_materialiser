"""Provider factory: maps the PROVIDER config value to a concrete DocumentAI.

To add a provider (e.g. a self-hosted OCR+PII endpoint), implement DocumentAI in
a new module and register it here. Nothing else in the pipeline changes.
"""
from __future__ import annotations

from ..config import Settings
from .base import DocumentAI


def get_provider(settings: Settings) -> DocumentAI:
    provider = settings.provider
    if provider == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(
            api_key=settings.api_key, model=settings.model,
            cache_prompt=settings.cache_prompt, cache_ttl=settings.cache_ttl_seconds,
        )

    if provider == "vertex":
        from .vertex import VertexProvider

        return VertexProvider(
            model=settings.model, project=settings.vertex_project,
            location=settings.vertex_location,
            cache_prompt=settings.cache_prompt, cache_ttl=settings.cache_ttl_seconds,
        )

    raise ValueError(
        f"Unknown PROVIDER={provider!r}. Implement it in anonymizer/llm/ and "
        f"register it in factory.get_provider."
    )
