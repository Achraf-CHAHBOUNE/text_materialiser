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


def test_json_null_is_empty_not_the_word_none():
    from anonymizer.llm.gemini import _s

    assert _s(None) == ""
    assert _s("  58 ") == "58"


def test_a_text_batch_too_large_for_one_reply_is_split_not_lost():
    from anonymizer.llm.base import BatchResult, PIIEntity
    from anonymizer.llm.gemini import GeminiProvider, TruncatedResponse

    calls: list[int] = []

    class _Provider(GeminiProvider):
        MIN_SPLIT_CHARS = 10

        def __init__(self):
            pass

        def _generate(self, contents, prompt, key, max_output=0):
            calls.append(len(contents[0]))
            return contents[0]

        def _to_result(self, resp, include_pages):
            if len(resp) > 40:
                raise TruncatedResponse("too big")
            return BatchResult(pii=[PIIEntity(resp.strip()[:5], "name")])

    text = "\n".join(f"line {i:02d} text" for i in range(8))
    result = _Provider().process_text(text)
    assert len(result.pii) >= 2, "both halves must contribute"
    assert max(calls) == len(text) and min(calls) <= 40


_AR = "ن"   # an Arabic letter, so the garble check reads the text as Arabic


def _ocr_provider(replies):
    """A GeminiProvider whose model returns `replies` in turn (page lists)."""
    from anonymizer.llm.base import BatchResult
    from anonymizer.llm.gemini import GeminiProvider

    class _Usage:
        prompt_token_count, candidates_token_count, cached_content_token_count = 10, 5, 0

    class _R:
        def __init__(self, pages):
            self.pages, self.usage_metadata, self.candidates, self.text = pages, _Usage(), [], ""

    class _P(GeminiProvider):
        def __init__(self):
            self.calls = []
            self._replies = list(replies)

        def _generate(self, contents, prompt, key, max_output=0):
            self.calls.append(key)
            return _R(self._replies.pop(0) if self._replies else [_AR * 900])

        def _to_result(self, resp, include_pages):
            return BatchResult(pages=resp.pages, output_tokens=5, input_tokens=10)

        def _split_and_process(self, pdf_bytes, page_count):
            self.split = page_count
            return BatchResult(pages=[_AR * 900] * page_count, input_tokens=1, output_tokens=1)

    return _P()


def test_a_thin_multi_page_transcription_is_retried_then_split():
    """Only the last page came back on every attempt: split and read page by page."""
    thin = ["", "", "لهذه الأسباب قضت محكمة النقض برفض الطلب"]
    p = _ocr_provider([thin, thin, thin])
    result = p.process_pdf(b"%PDF", page_count=3)
    assert p.split == 3
    assert len(result.pages) == 3 and all(len(x) == 900 for x in result.pages)
    assert result is not None


def test_every_attempt_is_counted_in_the_cost():
    """Discarded attempts were paid for; leaving them out under-reports the hard scans."""
    thin = ["", "", "short"]
    good = [_AR * 900] * 3
    p = _ocr_provider([thin, good])
    result = p.process_pdf(b"%PDF", page_count=3)
    assert result.input_tokens == 20 and result.output_tokens == 10


def test_the_best_attempt_is_kept_when_none_is_complete():
    one_page = [_AR * 110]           # below the single-page floor, but the most text
    p = _ocr_provider([[_AR * 50], one_page, [_AR * 10]])
    result = p.process_pdf(b"%PDF", page_count=1)
    assert result.pages == one_page



# --- quotes the model forgot to escape -----------------------------------------
def test_a_quotation_with_an_unescaped_closing_quote_is_repaired():
    """The shape that made 32 rulings unprocessable (and, before, 63 empty files).

    The model escapes the opening quote of a quoted legal text but not the closing
    one, which ends the JSON string early.
    """
    reply = ('{"pages": ["بعلة: \\"أنه طبقا لمقتضيات الفصل 1241 من ق. ل.ع"، تعتبر أموال '
             'المدين ضمانا عاما"], "pii": [{"text": "محمد العلوي", "type": "name"}]}')
    d = _parse_json(reply)
    assert "الفصل 1241" in d["pages"][0] and "ضمانا عاما" in d["pages"][0]
    assert [e["text"] for e in d["pii"]] == ["محمد العلوي"]


def test_several_stray_quotes_across_pages_are_all_repaired():
    reply = ('{"pages": ["قال \\"أولا" ثم", "وقال \\"ثانيا" أيضا"], '
             '"pii": [{"text": "زيد"}, {"text": "عمرو"}]}')
    d = _parse_json(reply)
    assert len(d["pages"]) == 2 and len(d["pii"]) == 2


def test_a_repair_that_would_lose_a_name_entry_is_refused():
    """Better no document than one redacted for fewer names than the model found."""
    from anonymizer.llm.gemini import _require_every_entry

    raw = '{"pages": ["x"], "pii": [{"text": "زيد"}, {"text": "عمرو"}]}'
    with pytest.raises(UnparseableResponse):
        _require_every_entry(raw, {"pages": ["x"], "pii": [{"text": "زيد"}]})


def test_well_formed_json_never_goes_through_the_repair():
    from anonymizer.llm import gemini

    called = []
    real = gemini._repair_stray_quotes
    gemini._repair_stray_quotes = lambda t: called.append(t) or real(t)
    try:
        _parse_json('{"pages": ["نص"], "pii": []}')
    finally:
        gemini._repair_stray_quotes = real
    assert called == []


def test_the_guard_refuses_a_repair_that_glues_two_names_into_one():
    """A missing comma is not a stray quote; blindly "repairing" it folds two
    entries into one mangled value, and the second name would never be redacted."""
    with pytest.raises(UnparseableResponse, match="kept 1 of 2"):
        _parse_json('{"pages": ["x"], "pii": [{"text": "زيد"} {"text": "عمرو"}]}')
