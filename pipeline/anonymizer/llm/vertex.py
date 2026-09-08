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
import json as _json
import shutil as _shutil
import subprocess

from google.oauth2.credentials import Credentials as _OAuthCredentials

from .gemini import GeminiProvider


class _GcloudSessionCredentials(_OAuthCredentials):
    """Refreshable credentials backed by the local gcloud session.

    Used only when ADC is not configured. Subclasses the real OAuth credential class
    (so google-auth/genai find every attribute they expect) and re-shells to gcloud
    before the token expires — a raw token lasts ~1h, which would otherwise kill a
    multi-hour run.

    The expiry is read from the token itself, never guessed. `gcloud auth
    print-access-token` hands back a *cached* token rather than minting a new one, so
    stamping a fixed lifetime on every refresh eventually declares a token good well
    past its real death: the credential then never refreshes again and every request
    401s until the run is killed. Asking the token what it has left costs one call per
    refresh (roughly hourly) and cannot drift.
    """

    # Refresh this long before the real expiry, so in-flight requests can't race it.
    _SAFETY = _dt.timedelta(minutes=5)
    # Used only when the token's real lifetime can't be read — short on purpose, so we
    # re-check soon rather than trusting a guess.
    _BLIND = _dt.timedelta(minutes=10)

    def __init__(self) -> None:
        super().__init__(token=self._fetch())
        self._stamp()

    @staticmethod
    def _fetch() -> str:
        exe = _shutil.which("gcloud") or "gcloud"
        out = subprocess.run(
            [exe, "auth", "print-access-token"],
            capture_output=True, text=True, shell=(exe == "gcloud"),
        )
        tok = (out.stdout or "").strip()
        # A non-zero exit with output on stdout would otherwise install an error
        # message as the bearer token and fail much later, far from the cause.
        if out.returncode != 0 or not tok or not tok.startswith("ya29."):
            raise RuntimeError(
                "No Google credentials. Run `gcloud auth application-default login` "
                "(or set GOOGLE_APPLICATION_CREDENTIALS). "
                f"gcloud said: {(out.stderr or '').strip()[:200]}"
            )
        return tok

    def _remaining(self) -> _dt.timedelta | None:
        """What this token actually has left, or None if it can't be determined."""
        try:
            import urllib.request

            with urllib.request.urlopen(
                "https://oauth2.googleapis.com/tokeninfo?access_token=" + self.token,
                timeout=10,
            ) as r:
                return _dt.timedelta(seconds=int(_json.load(r)["expires_in"]))
        except Exception:
            return None

    def _stamp(self) -> None:
        left = self._remaining()
        window = (left - self._SAFETY) if left else self._BLIND
        # Never stamp an expiry in the past, or google-auth refresh-loops.
        self.expiry = _dt.datetime.utcnow() + max(window, _dt.timedelta(minutes=1))

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
