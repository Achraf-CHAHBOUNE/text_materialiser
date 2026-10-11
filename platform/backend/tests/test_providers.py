"""Choosing where the model step sends its requests.

Three gateways, two request shapes. The rules here are the ones that would otherwise
be found out the hard way, 16,000 requests into a run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import classify_rulings as cr


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload or {}, text

    def json(self):
        return self._payload


class FakeClient:
    """Answers with whatever it was given, and remembers what it was asked."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, params=None, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "params": params or {},
                           "headers": headers or {}, "body": json})
        return self.responses.pop(0)


def _ask(client, provider, model="m"):
    return cr.ask(client, "نص القرار", "مدنية", ["كراء"],
                  key="KEY", model=model, budget=cr.Budget(), provider=provider)


def test_gemini_is_authenticated_by_query_and_the_others_by_header():
    """Sending a Gemini key as a bearer token, or an OpenAI key as ?key=, fails in a
    way that looks like a broken model rather than a misplaced credential."""
    for provider in cr.PROVIDERS:
        c = FakeClient(FakeResponse(200, _reply(provider)))
        _ask(c, provider)
        call = c.calls[0]
        if cr.PROVIDERS[provider]["style"] == "gemini":
            assert call["params"].get("key") == "KEY"
            assert "Authorization" not in call["headers"]
        else:
            assert call["headers"]["Authorization"] == "Bearer KEY"
            assert "key" not in call["params"]


def _reply(provider):
    body = '{"theme": "كراء", "abstract": "' + "ا" * 80 + '"}'
    if cr.PROVIDERS[provider]["style"] == "gemini":
        return {"usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4},
                "candidates": [{"content": {"parts": [{"text": body}]}}]}
    return {"usage": {"prompt_tokens": 9, "completion_tokens": 4},
            "choices": [{"message": {"content": body}}]}


def test_every_provider_s_reply_shape_is_understood():
    for provider in cr.PROVIDERS:
        got, err = _ask(FakeClient(FakeResponse(200, _reply(provider))), provider)
        assert err is None, provider
        assert got["theme"] == "كراء", provider


def test_the_free_tier_refusal_is_named_not_counted_as_a_failure():
    """OpenCode reserves its -free models for its own app. That is not a transient
    error and no amount of retrying fixes it, so it must be told apart from one."""
    refusal = FakeResponse(
        403, {"error": {"type": "FreeTierError",
                        "message": "OpenCode's free tier can only be used from within OpenCode"}},
        text='{"error":{"message":"OpenCode\'s free tier can only be used from within OpenCode"}}')
    got, err = _ask(FakeClient(refusal), "opencode", model="space-bunny-free")
    assert got is None
    assert err == "FREE_TIER_LOCKED"


def test_a_refusal_is_not_retried():
    """Four retries times 16,585 rulings is a lot of requests to send at a wall."""
    refusal = FakeResponse(
        403, {}, text='{"error":{"message":"free tier can only be used from within OpenCode"}}')
    c = FakeClient(refusal)
    _ask(c, "opencode", model="space-bunny-free")
    assert len(c.calls) == 1


def test_an_ordinary_server_error_is_still_retried():
    ok = FakeResponse(200, _reply("opencode"))
    c = FakeClient(FakeResponse(503, {}, text="busy"), ok)
    got, err = _ask(c, "opencode")
    assert err is None and len(c.calls) == 2
