"""Over-redaction guard + garbled-OCR detection (problems found on real scans)."""
from anonymizer.core.redactor import redact_text
from anonymizer.llm.base import PIIEntity
from anonymizer.pipeline import _ocr_garbled


def test_short_value_does_not_over_redact():
    # a 1-char flagged value must not shred the document
    clean, _ = redact_text("محكمة النقض باسم الملك رقم", [PIIEntity("م", "name")], "XXXXXXX")
    assert "XXXXXXX" not in clean and "محكمة" in clean and "باسم" in clean


def test_ocr_garbled_flags_presentation_forms():
    bad = "".join(chr(0xFB50 + (i % 200)) for i in range(500))
    assert _ocr_garbled(bad)


def test_ocr_garbled_flags_near_empty_arabic():
    assert _ocr_garbled("12345 67890 " * 60 + "قرار")   # almost no Arabic


def test_ocr_garbled_passes_clean_ruling():
    good = "محكمة النقض قرار عدد ٦٢١ الصادر في الملف المدني بشأن نزاع عقاري " * 20
    assert not _ocr_garbled(good)
