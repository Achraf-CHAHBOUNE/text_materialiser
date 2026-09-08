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


def test_a_single_result_object_in_an_array_is_unwrapped():
    d = _parse_json('[{"pii": [{"text": "محمد", "type": "name"}], "level": "نقض"}]')
    assert d["level"] == "نقض"
    assert d["pii"][0]["text"] == "محمد"


def test_two_result_objects_are_merged_so_no_pii_is_dropped():
    """A PDF holding two rulings comes back as two objects.

    Five documents failed on this shape. Taking only the first object would drop
    the second ruling's names and ship them unredacted, so they must be merged.
    """
    d = _parse_json(
        '[{"pii": [{"text": "محمد", "type": "name"}], "level": "نقض", "pages": ["p1"]},'
        ' {"pii": [{"text": "سعاد", "type": "name"}], "level": "", "pages": ["p2"]}]'
    )
    assert [e["text"] for e in d["pii"]] == ["محمد", "سعاد"]
    assert d["pages"] == ["p1", "p2"]
    assert d["level"] == "نقض"          # first non-empty scalar wins


def test_a_wrapped_object_is_not_mistaken_for_a_pii_entry():
    d = _parse_json('[{"pages": ["page one"], "pii": []}]')
    assert d["pages"] == ["page one"]
    assert d["pii"] == []


class _Cand:
    def __init__(self, reason): self.finish_reason = reason


class _Resp:
    def __init__(self, text, reason=None):
        self.text = text
        self.candidates = [_Cand(reason)] if reason else []
        self.usage_metadata = None


def test_a_reply_cut_off_at_the_token_cap_is_not_salvaged_into_partial_data():
    """The dangerous shape: a half-written pii array parses as valid JSON.

    Redacting only the names that fit under the cap would ship the rest, and the
    leak gate would not notice because it only re-scans the values it was handed.
    """
    from anonymizer.llm.gemini import GeminiProvider, TruncatedResponse

    truncated = '{"pages": ["page one"], "pii": [{"text": "محمد", "type": "name"}'
    with pytest.raises(TruncatedResponse):
        GeminiProvider._check_complete(_Resp(truncated, "MAX_TOKENS"))


def test_a_complete_reply_passes_the_truncation_check():
    from anonymizer.llm.gemini import GeminiProvider

    GeminiProvider._check_complete(_Resp('{"pii": []}', "STOP"))
    GeminiProvider._check_complete(_Resp('{"pii": []}'))


def test_salvage_alone_cannot_be_trusted_to_reject_a_truncated_reply():
    """Why the finish_reason check exists rather than relying on invalid JSON.

    Most truncations do leave unparseable JSON, but not all: when the cut lands
    after a complete "pii" array the salvage recovers that array and returns it as
    a whole answer. Nothing downstream can tell the reply was cut short.
    """
    cut_after_pii = ('{"pii": [{"text": "محمد"}, {"text": "سعاد"}], '
                     '"own": {"court": "محك')
    d = _parse_json(cut_after_pii)
    assert len(d["pii"]) == 2          # accepted, with no sign it was truncated
    assert d.get("pages", []) == []    # the rest of the reply is simply gone


def test_the_retry_ceiling_stays_inside_what_the_api_accepts():
    """maxOutputTokens must be < 65536; 65536 itself is a hard 400."""
    from anonymizer.llm.gemini import GeminiProvider

    assert GeminiProvider.MAX_OUTPUT_CEILING < 65536


def test_a_batch_too_large_for_any_budget_is_split_rather_than_lost():
    """When even the API maximum cannot hold the reply, halve the batch.

    One document failed every retry because six pages of a garbled scan could not
    fit in one reply at any budget the API accepts.
    """
    import io

    from pypdf import PdfWriter

    from anonymizer.llm.base import BatchResult
    from anonymizer.llm.gemini import GeminiProvider, TruncatedResponse

    writer = PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    pdf = buf.getvalue()

    seen: list[int] = []

    class _Provider(GeminiProvider):
        def __init__(self):
            pass

        def process_pdf(self, pdf_bytes, page_count=1):
            seen.append(page_count)
            # Anything wider than one page is still too big for a reply.
            if page_count > 1:
                return self._split_and_process(pdf_bytes, page_count)
            return BatchResult(pages=["p"], output_tokens=1)

    result = _Provider().process_pdf(pdf, 4)
    assert result.pages == ["p"] * 4, "every page must survive the split"
    assert 1 in seen and 4 in seen, f"expected halving down to single pages: {seen}"
