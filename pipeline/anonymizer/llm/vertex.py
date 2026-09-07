"""Vertex AI provider — same Gemini model, enterprise auth and quota.

Identical behaviour to the direct Gemini API provider (same prompts, same parsing,
same prompt caching); only the client differs:

  - auth:   Google Cloud IAM, not an API key
  - quota:  per GCP *project* (not per key) — so an API-key pool is unnecessary
  - data:   documents are sent inline per request (online prediction). Nothing is
            written to Cloud Storage, so no raw PII is ever at rest in the cloud.

Set PROVIDER=vertex plus VERTEX_PROJECT / VERTEX_LOCATION in .env.

Credentials are resolved in this order:
  1. Application Default Credentials — `gcloud auth application-default login`
     or GOOGLE_APPLICATION_CREDENTIALS=<service-account.json>   (preferred)
  2. Fallback: the logged-in gcloud session (`gcloud auth print-access-token`),
     wrapped so it auto-refreshes — a raw token expires in ~1h, which would
     otherwise kill a multi-hour batch run.
"""
from __future__ import annotations

import datetime as _dt
import subprocess

from google.oauth2.credentials import Credentials as _OAuthCredentials

from .gemini import GeminiProvider


class _GcloudSessionCredentials(_OAuthCredentials):
    """Refreshable credentials backed by the local gcloud session.

    Used only when ADC is not configured. Subclasses the real OAuth credential class
    (so google-auth/genai find every attribute they expect) and re-shells to gcloud
    before the token expires — a raw token lasts ~1h, which would otherwise kill a
    multi-hour run.
    """

    def __init__(self) -> None:
        super().__init__(token=self._fetch())
        self._stamp()

    @staticmethod
    def _fetch() -> str:
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, shell=True,
        )
        tok = (out.stdout or "").strip()
        if not tok:
            raise RuntimeError(
                "No Google credentials. Run `gcloud auth application-default login` "
                "(or set GOOGLE_APPLICATION_CREDENTIALS)."
            )
        return tok

    def _stamp(self) -> None:
        # gcloud tokens last ~60 min; expire ours early so it refreshes in good time.
        self.expiry = _dt.datetime.utcnow() + _dt.timedelta(minutes=45)

    def refresh(self, request=None) -> None:  # noqa: ARG002 - signature fixed by google-auth
        self.token = self._fetch()
        self._stamp()


def _credentials():
    """ADC if configured, else the gcloud session (auto-refreshing)."""
    try:
        import google.auth
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return creds
    except Exception:
        return _GcloudSessionCredentials()


class VertexProvider(GeminiProvider):
    """Gemini on Vertex AI. Reuses every method of GeminiProvider; only auth changes."""

    def __init__(self, model: str, project: str, location: str = "us-central1",
                 cache_prompt: bool = True, cache_ttl: int = 3600):
        if not project:
            raise ValueError("VERTEX_PROJECT is not set (see .env).")
        from google import genai

        self._genai = genai
        # vertexai=True switches the SDK to the Vertex endpoint.
        self._client = genai.Client(
            vertexai=True, project=project, location=location, credentials=_credentials())
        self._model = model
        self._cache_prompt = cache_prompt
        self._cache_ttl = cache_ttl
        self._caches: dict[str, str | None] = {}
        self.project = project
        self.location = location
