"""Recall boosters: reversed name order + deterministic structured-PII removal."""
from anonymizer.core.redactor import redact_structured, redact_text
from anonymizer.llm.base import PIIEntity


def test_reversed_name_order_is_redacted():
    # model flagged "الغريب محمد"; the text writes it the other way round
    clean, rep = redact_text("حضر محمد الغريب أمام المحكمة",
                             [PIIEntity("الغريب محمد", "name")], "XXXXXXX")
    assert "الغريب" not in clean and "محمد الغريب" not in clean
    assert "الغريب محمد" in rep.replaced


def test_both_orders_from_one_flagged_value():
    # a single flagged value must clear BOTH orders when both appear in the text
    txt = "بينه وبين الغريب محمد، وأدلى محمد الغريب بمقال"
    clean, _ = redact_text(txt, [PIIEntity("محمد الغريب", "name")], "XXXXXXX")
    assert "الغريب" not in clean and "محمد" not in clean


def test_structured_pii_removed_by_pattern():
    text = "للتواصل: ahmed@mail.com أو الهاتف 0612345678 والبطاقة الوطنية AB123456"
    clean, n = redact_structured(text, "XXXXXXX")
    assert n >= 3
    assert "@mail.com" not in clean and "0612345678" not in clean and "AB123456" not in clean


def test_structured_keeps_normal_numbers():
    # a case/file number with slashes must NOT be treated as structured PII
    text = "الملف عدد 2013/6/1/4591 القرار 679"
    clean, n = redact_structured(text, "XXXXXXX")
    assert n == 0 and "2013/6/1/4591" in clean
