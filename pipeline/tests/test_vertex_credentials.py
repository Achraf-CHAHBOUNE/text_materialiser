"""The gcloud-session credential must never outlive its real token.

`gcloud auth print-access-token` returns a *cached* token rather than minting a
fresh one. A credential that stamps a fixed lifetime on each refresh therefore
declares a recycled token valid past its real death, stops refreshing, and every
subsequent request 401s until the run is killed — which is exactly what halted a
3,239-document run at 86%.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from anonymizer.llm.vertex import _GcloudSessionCredentials as Creds


class _FixedToken(Creds):
    """gcloud handing back the same cached token, with its real life ticking down."""

    def __init__(self, life_minutes: float):
        self._life = _dt.timedelta(minutes=life_minutes)
        self.fetches = 0
        super().__init__()

    def _fetch(self) -> str:          # type: ignore[override]
        self.fetches += 1
        return "ya29.cached-token"

    def _remaining(self):             # type: ignore[override]
        return self._life


def test_expiry_tracks_the_real_token_life_not_a_fixed_guess():
    c = _FixedToken(life_minutes=58)
    left = (c.expiry - _dt.datetime.utcnow()).total_seconds() / 60
    assert 50 < left < 55, f"expected ~53min (58 - 5 safety), got {left:.1f}"


def test_refreshing_a_recycled_token_cannot_extend_it_past_its_death():
    """The actual regression: refresh must not re-stamp a full lifetime."""
    c = _FixedToken(life_minutes=58)
    death = _dt.datetime.utcnow() + _dt.timedelta(minutes=58)

    # Simulate the run: token now has 13 minutes left, google-auth calls refresh,
    # gcloud returns the SAME token. Expiry must stay inside the real death.
    c._life = _dt.timedelta(minutes=13)
    c.refresh()
    assert c.expiry < death, "refresh pushed expiry past the token's real expiry"

    c._life = _dt.timedelta(minutes=2)
    c.refresh()
    assert c.expiry < death


def test_expiry_is_never_stamped_in_the_past():
    """A past expiry would make google-auth refresh-loop on every request."""
    c = _FixedToken(life_minutes=1)          # less than the 5-minute safety margin
    assert c.expiry > _dt.datetime.utcnow()


def test_a_failed_gcloud_call_raises_instead_of_installing_a_junk_token():
    """Otherwise an error message becomes the bearer token and fails far from its cause."""
    import subprocess

    class _Result:
        returncode, stdout, stderr = 1, "", "You do not currently have an active account"

    orig = subprocess.run
    subprocess.run = lambda *a, **k: _Result()          # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError, match="No Google credentials"):
            Creds._fetch()
    finally:
        subprocess.run = orig


def test_a_non_token_on_stdout_is_rejected():
    import subprocess

    class _Result:
        returncode, stdout, stderr = 0, "WARNING: some gcloud notice", ""

    orig = subprocess.run
    subprocess.run = lambda *a, **k: _Result()          # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError):
            Creds._fetch()
    finally:
        subprocess.run = orig
