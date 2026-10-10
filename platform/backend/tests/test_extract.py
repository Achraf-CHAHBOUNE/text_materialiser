"""Reading a ruling once and taking everything it carries.

The outcome is the field this adds: the pipeline left it empty on all 29,383 rulings
even though the court prints it, usually twice. These are the shapes it prints it in.
"""
import extract


def test_the_outcome_as_a_heading_of_its_own():
    assert extract.outcome(
        "محكمة النقض\nالقرار عدد 942\nرفض الطلب\nباسم جلالة الملك") == "رفض الطلب"


def test_the_outcome_from_the_closing_when_no_heading_carries_it():
    """Most rulings print it only here, which is why the heading alone found a third
    of the corpus and reading both finds 84%."""
    assert extract.outcome(
        "محكمة النقض\nفي الملف المدني عدد 2021/4/1/4836\n" + "حيث إن الطاعن يعيب. " * 40 +
        "\nلهذه الأسباب\nقضت محكمة النقض بنقض وإحالة القضية على نفس المحكمة.") == "نقض وإحالة"


def test_spellings_of_one_decision_fold_onto_one_value():
    """So a listing can group by it: عدم قبول الطلب is not a second kind of outcome."""
    a = extract.outcome("محكمة النقض\nعدم قبول الطلب\nباسم جلالة الملك")
    b = extract.outcome("محكمة النقض\nعدم القبول\nباسم جلالة الملك")
    assert a == b == "عدم القبول"


def test_the_longer_spelling_wins_over_the_shorter_one_inside_it():
    """عدم القبول is contained in عدم قبول الطلب; matching the short one first would
    report the wrong decision for every ruling that uses the long one."""
    assert extract.outcome(
        "محكمة النقض\nفي الملف\n" + "حيث. " * 30 +
        "\nلهذه الأسباب قضت محكمة النقض بعدم قبول الطلب وتحميل الطالب المصاريف."
    ) == "عدم القبول"


def test_a_ruling_that_states_no_outcome_gets_none():
    assert extract.outcome("محكمة النقض\nقرار محكمة النقض\nرقم 607/5\nباسم جلالة الملك") == ""


def test_the_closing_is_only_read_near_the_end():
    """The words appear in argument too; only the court's own closing decides."""
    text = ("محكمة النقض\n"
            "حيث يعيب الطاعن أنه سبق أن قضت محكمة النقض برفض الطلب في نازلة مشابهة.\n"
            + "ونصت المادة. " * 400)
    assert extract.outcome(text) == ""


def test_tatweel_in_the_heading_does_not_hide_it():
    assert extract.outcome("محكمة النقض\nرفـض الطلــب\nباسم جلالة الملك") == "رفض الطلب"


def test_text_near_the_end_is_not_an_outcome_unless_the_court_is_closing():
    """Many scans end mid-argument. The decision words appear there, but without
    لهذه الأسباب or قضت محكمة النقض the court has not said what it decided."""
    text = ("محكمة النقض\nفي الملف المدني عدد 2021/4/1/4836\n"
            + "ونصت المادة. " * 400
            + "وانتهى الطاعن إلى أن ما قضي به من رفض الطلب لا سند له في القانون")
    assert extract.outcome(text) == ""
