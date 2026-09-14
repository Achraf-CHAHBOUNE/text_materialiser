"""The four listing fields: decision number, date, chamber, lower-court city.

Cases are taken from what the model actually returned on a 3,236-ruling corpus.
"""
from __future__ import annotations

import pytest

from anonymizer.core.fields import (canonical_city, chamber_from_text, display_date,
                                    display_decision_no, origin_city)
from anonymizer.core.identifiers import Ident


@pytest.mark.parametrize("raw, want", [
    ("58", "58"), ("058", "58"),
    ("33/1", "33"),        # decision / panel section
    ("2/96", "96"),        # section / decision -- the single digit is the section
    ("154/2", "154"),
    ("٥٨", "58"),          # Arabic-Indic digits
    ("None", ""), ("غير محدد", ""), ("", ""),
    ("2019/1/2/669", ""),  # a file number in the wrong field is not shown
])
def test_decision_number(raw, want):
    assert display_decision_no(raw) == want


@pytest.mark.parametrize("raw, want", [
    ("08 فبراير 2022", "08/02/2022"),
    ("16 أكتوبر2018", "16/10/2018"),
    ("18 /07 /2016", "18/07/2016"),
    ("2021-02-23", "23/02/2021"),
    ("12 (بریل 2022", "12/04/2022"),   # OCR: hamza lost, Persian ya
    ("17 وجنبر 2008", "17/12/2008"),   # OCR: د read as و
    ("21 ماي 2019", "21/05/2019"),
    ("الصادر بتاريخ 12 رجب 1439 موافق 29 مارس 2018", "29/03/2018"),  # Hijri skipped
    ("2014", ""),                      # a year alone is not a date
    ("None", ""),
    ("31 فبراير 20222", ""),
])
def test_display_date(raw, want):
    assert display_date(raw) == want


def test_a_hijri_month_is_never_coerced_into_a_gregorian_one():
    assert display_date("12 رجب 1439") == ""


@pytest.mark.parametrize("header, want", [
    ("قرار محكمة النقض عدد 53 الصادر بتاريخ 08 فبراير 2022 في الملف الشرعي رقم 2020/2/2/516", "أحوال شخصية"),
    ("في الملف المدني عدد 1234/1/1/2019", "مدنية"),
    ("ملف شرعي عدد 12/2/1/2015", "أحوال شخصية"),
    ("محكمة النقض - غرفة الأحوال الشخصية والميراث", "أحوال شخصية"),
    ("الغرفة التجارية - القرار عدد 5", "تجارية"),
    ("في الملف الجنحي عدد 5/6/1/2010", "جنائية"),
    ("قرار محكمة النقض عدد 12 بتاريخ 2019", ""),
])
def test_chamber_is_read_from_what_the_ruling_says_about_itself(header, want):
    assert chamber_from_text(header) == want


def test_a_lower_courts_file_type_deep_in_the_text_is_ignored():
    text = "قرار محكمة النقض " + "نص " * 400 + "في الملف المدني عدد 44/2015 الصادر عن المحكمة الابتدائية"
    assert chamber_from_text(text) == ""


@pytest.mark.parametrize("text, want", [
    ("محكمة الاستئناف ببني ملال", "بني ملال"),
    ("المحكمة الابتدائية بالدار البيضاء", "الدار البيضاء"),
    ("بالبيضاء", "الدار البيضاء"),
    ("محكمة الاستئناف بأكادير", "أكادير"),
    ("ابن سليمان", "بن سليمان"),
    ("المحكمة الإسلامية", ""),          # "سلا" inside another word is not Salé
    ("فاسد", ""),
])
def test_canonical_city(text, want):
    assert canonical_city(text) == want


def test_origin_city_prefers_the_appeal_court_and_skips_cassation():
    refs = [Ident(court="محكمة النقض"), Ident(court="المحكمة الابتدائية بصفرو"),
            Ident(court="محكمة الاستئناف بفاس")]
    assert origin_city(refs) == ("فاس", "appeal")


def test_origin_city_tolerates_ocr_split_court_names():
    assert origin_city([Ident(court="محكمة ال ستئناف", city="مراكش")]) == ("مراكش", "appeal")
    assert origin_city([Ident(court="المحكمة الا بتدائية بتيفلت")]) == ("تيفلت", "first-instance")


def test_origin_city_falls_back_to_the_ruling_text():
    text = "وحيث إن القرار المطعون فيه الصادر عن محكمة الاستئناف بطنجة قضى"
    assert origin_city([], text) == ("طنجة", "appeal-in-text")


def test_a_foreign_court_is_not_an_origin():
    assert origin_city([Ident(court="محكمة", city="مونبوليي")]) == ("", "")
