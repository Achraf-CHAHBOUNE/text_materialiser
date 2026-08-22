"""Leak-test release gate."""
from anonymizer.core.leaktest import leak_scan


def test_clean_output_passes():
    out = "حكمت المحكمة على XXXXXXX بأداء المبلغ المحكوم به"
    r = leak_scan(out, ["محمد العلوي"])
    assert r.passed and r.hits == 0


def test_surviving_name_fails():
    out = "حكمت المحكمة على محمد العلوي بأداء المبلغ"
    r = leak_scan(out, ["محمد العلوي"])
    assert not r.passed and r.hits >= 1 and "محمد العلوي" in r.leaked


def test_line_wrapped_name_caught():
    out = "على محمد\nالعلوي في"
    assert not leak_scan(out, ["محمد العلوي"]).passed


def test_diacritics_survival_caught_by_collapsed_pass():
    # Name in the output carries harakat; the flagged value does not. The redactor's
    # token regex would miss this — the collapsed pass must catch it.
    out = "على مُحَمَّد العَلَوِي في"
    assert not leak_scan(out, ["محمد العلوي"]).passed


def test_short_value_no_false_positive():
    # A 1-2 char value must not trigger the collapsed substring pass.
    out = "المحكمة الابتدائية بالرباط"
    assert leak_scan(out, ["ا"]).passed


def test_empty_values_pass():
    assert leak_scan("أي نص", ["", "   "]).passed
