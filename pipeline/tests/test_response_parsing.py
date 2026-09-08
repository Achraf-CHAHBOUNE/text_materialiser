"""Model replies that aren't the expected JSON object must never ship unredacted.

The default that looks safe -- "no PII found" -- is the dangerous one: the
document is written out with nothing removed, and the leak gate has no values to
scan, so it passes and the file ships as clean. These cases must fail loudly and
send the document to quarantine instead.
"""
from __future__ import annotations

import pytest

from anonymizer.llm.gemini import UnparseableResponse, _parse_json


def test_a_normal_object_parses():
    d = _parse_json('{"pii": [{"text": "محمد", "type": "name"}], "level": "نقض"}')
    assert d["pii"][0]["text"] == "محمد"
    assert d["level"] == "نقض"


def test_a_fenced_object_parses():
    d = _parse_json('```json\n{"pii": [], "pages": ["a"]}\n```')
    assert d["pages"] == ["a"]


def test_a_legitimately_empty_pii_list_is_kept():
    """A real 'I found nothing' answer is valid and must not raise."""
    assert _parse_json('{"pii": [], "pages": []}')["pii"] == []


def test_a_bare_array_is_read_as_the_pii_list():
    """The regression: the model drops the wrapper and returns just the array.

    This used to crash with "'list' object has no attribute 'get'" and lose the
    document.
    """
    d = _parse_json('[{"text": "محمد", "type": "name"}]')
    assert d["pii"][0]["text"] == "محمد"


def test_an_object_embedded_in_prose_is_salvaged():
    d = _parse_json('Here you go:\n{"pii": [{"text": "x"}]}\nhope that helps')
    assert d["pii"] == [{"text": "x"}]


@pytest.mark.parametrize("reply", [
    "",                       # empty response
    "   ",
    "I'm sorry, I can't help with that.",   # refusal, no JSON at all
    "[]",                     # empty array: carries no PII claim
    '"just a string"',
    "42",
    "null",
])
def test_an_unusable_reply_raises_instead_of_reporting_no_pii(reply):
    with pytest.raises(UnparseableResponse):
        _parse_json(reply)
