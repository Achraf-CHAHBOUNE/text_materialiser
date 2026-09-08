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


def test_honorific_prefix_fallback():
    # Model flagged the name WITH a title; text has it WITHOUT -> must still redact.
    text = "حضر عبد الهادي ايت المقدم الجلسة"
    clean, report = redact_text(text, [PIIEntity("السيد عبد الهادي ايت المقدم", "name")], TOKEN)
    assert "عبد الهادي" not in clean
    assert report.unmatched == []


def test_alef_variant_tolerance():
    # Text uses 'آيت' (madda) while the flagged value uses plain 'ايت'.
    text = "حضر عبد الهادي آيت المقدم"
    clean, _ = redact_text(text, [PIIEntity("عبد الهادي ايت المقدم", "name")], TOKEN)
    assert "الهادي" not in clean


# --- tatweel / diacritics in the FLAGGED VALUE ---------------------------------
def test_a_name_flagged_with_tatweel_still_redacts_the_plain_spelling():
    """Three of eleven real leak-quarantines in a 3,239-document run were this.

    The model echoes a name exactly as the OCR rendered it ("باســــــو"), and the
    pattern used to require those decorations back in the same places, so the plain
    spelling in the text was never matched and the name shipped.
    """
    from anonymizer.core.redactor import redact_text
    from anonymizer.llm.base import PIIEntity

    for value, text in [("حسـنـات", "قضت المحكمة في حق حسنات بنت أحمد"),
                        ("نبيـة", "وحضرت نبية أمام المحكمة"),
                        ("باســــــو", "السيد باسو المدعي")]:
        out, _ = redact_text(text, [PIIEntity(text=value, type="name")], "XXXXXXX")
        assert "XXXXXXX" in out, f"{value!r} leaked"


def test_the_reverse_direction_still_matches():
    """Clean value, decorated text — this direction already worked; keep it working."""
    from anonymizer.core.redactor import redact_text
    from anonymizer.llm.base import PIIEntity

    out, _ = redact_text("وحضرت نبيـة أمام المحكمة",
                         [PIIEntity(text="نبية", type="name")], "XXXXXXX")
    assert "XXXXXXX" in out


def test_a_value_made_only_of_decoration_is_still_refused():
    """Stripping decoration must not let a junk value past the length guard."""
    from anonymizer.core.redactor import redact_text
    from anonymizer.llm.base import PIIEntity

    text = "محكمة النقض بالرباط"
    out, rep = redact_text(text, [PIIEntity(text="ــ", type="name")], "XXXXXXX")
    assert out == text
    assert "ــ" in rep.unmatched
