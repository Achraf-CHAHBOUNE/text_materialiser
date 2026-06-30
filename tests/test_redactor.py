"""Offline tests for local PII redaction (no LLM/API calls)."""
from anonymizer.core.redactor import redact_text
from anonymizer.llm.base import PIIEntity

TOKEN = "XXXXXXX"


def test_basic_name_and_address_redaction():
    text = (
        "ينوب عنها الأساتذة عبد العلي القصار ونجية منوبية طق طق.\n"
        "بشارع الحسن الثاني الرقم 140 الدار البيضاء ."
    )
    entities = [
        PIIEntity("عبد العلي القصار", "name"),
        PIIEntity("نجية منوبية طق طق", "name"),
        PIIEntity("شارع الحسن الثاني الرقم 140 الدار البيضاء", "address"),
    ]
    clean, report = redact_text(text, entities, TOKEN)
    assert "عبد العلي القصار" not in clean
    assert "نجية منوبية طق طق" not in clean
    assert TOKEN in clean
    assert len(report.replaced) == 3
    assert report.unmatched == []


def test_line_wrapped_name_is_redacted():
    # Name split across an OCR line break must still be caught (whitespace-flexible).
    text = "بواسطة نوابها الأساتذة عبد\nالعلي القصار وغيره"
    clean, _ = redact_text(text, [PIIEntity("عبد العلي القصار", "name")], TOKEN)
    assert "القصار" not in clean
    assert TOKEN in clean


def test_unmatched_is_reported_not_replaced():
    text = "نص لا يحتوي على الاسم"
    clean, report = redact_text(text, [PIIEntity("محمد العلوي", "name")], TOKEN)
    assert clean == text
    assert report.unmatched == ["محمد العلوي"]


def test_whitespace_insensitive_match():
    text = "السيد   محمد   العلوي هنا"
    clean, report = redact_text(text, [PIIEntity("محمد العلوي", "name")], TOKEN)
    assert "محمد" not in clean
    assert report.replaced == ["محمد العلوي"]
