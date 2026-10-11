"""Reading the subject a ruling files itself under.

The themes shown on the site are not ours: they are the words the court printed, so
every rule here is about taking that line faithfully and about refusing to guess when
the court printed nothing. The shapes come from the corpus, not from imagination -
each one is a line that actually appears in it.
"""
import headnotes


def test_reads_theme_sub_issues_qualifier_and_rule():
    h = headnotes.read(
        "محكمة النقض\nالقرار عدد 942\n"
        "الصادر بتاريخ 11 نونبر 2020 في الملف الجنائي عدد 2019/4/6/14842 "
        "جناية التزوير في محرر رسمي - عدم إبراز أركانها – أثره. "
        "إن المحكمة لم تبرز أركان جناية التزوير في محرر رسمي، ومنها النشاط المادي.\n"
        "باسم جلالة الملك")
    assert h.theme == "جناية التزوير في محرر رسمي"
    assert h.sub == ["عدم إبراز أركانها"]
    assert h.qualifier == "أثره"
    assert h.rule.startswith("إن المحكمة لم تبرز")


def test_no_headnote_is_none_not_a_guess():
    """Most civil rulings print the file-number line and nothing else."""
    assert headnotes.read(
        "محكمة النقض\nقرار محكمة النقض\nرقم 607/5\n"
        "الصادر بتاريخ 21/09/2021 في الملف المدني رقم 9334/1/5/2019\n"
        "باسم جلالة الملك وطبقا للقانون") is None


def test_file_number_printed_before_the_phrase():
    """The PDFs lose right-to-left order, so the number often comes first."""
    h = headnotes.read(
        "محكمة النقض\n"
        "الصادر بتاريخ 10 فبراير 2021 2019/3/6/12073 في الملف الجنحي رقم "
        "قرار جنحي - وصفه خطأ بصدوره حضوريا – أثره. البين أن القرار المتعرض عليه صدر غيابيا.")
    assert h.theme == "قرار جنحي"
    assert h.qualifier == "أثره"


def test_tolerates_the_ocr_misreading_of_the_file_word():
    h = headnotes.read(
        "محكمة النقض\nالصادر بتاريخ 27 شتنبر 2022 2019/7/1/9375 في المحلف الجنحي رقم "
        "ملك غابوي - تناقض الخبرات – أثره. البين أن نتيجة الخبرتين جاءت متناقضة.")
    assert h.theme == "ملك غابوي"


def test_petition_paragraph_is_not_read_as_a_headnote():
    """It names a file number too, and a page break can leave it opening mid-sentence,
    so no heading marks it: only its wording tells it apart."""
    assert headnotes.read(
        "محكمة النقض\nرقم 206\n"
        "بواسطة نائبها الأستاذ (س.ط)، الرامية إلى نقض القرار رقم 2020/532 الصادر عن "
        "محكمة الاستئناف بخريبكة بتاريخ 2020/12/08 في الملف عدد 2019/1401/783.") is None


def test_heading_decorated_with_tatweel_is_still_recognised():
    """باسـم جلالــة الملــك is a heading however it is spelled, and what follows it on
    the line belongs to the ruling's opening, not to a headnote."""
    assert headnotes.read(
        "محكمة النقض\nرقم 468/3\n"
        "باسـم جلالــة الملــك وطبقا للقانون في الملف المدني 3774/1/3/2018 "
        "تحفيظ - تعرض – أثره. وقع الحكم بعد ذلك.") is None


def test_a_chain_with_no_qualifier_is_still_read():
    h = headnotes.read(
        "محكمة النقض\n"
        "الصادر بتاريخ 07 شتنبر 2021 في الملف الشرعي عدد 2020/1/2/206 "
        "النسب – منازعة بعد وفاة المستلحق - وجوب إثبات الأب الحقيقي. "
        "الإقرار سبب من أسباب لحوق النسب، ويثبت به بصرف النظر عن ولادة المقر به.")
    assert h.theme == "النسب"
    assert h.qualifier == ""
    assert "الإقرار سبب" in h.rule


def test_normalise_groups_spellings_but_keeps_subjects_apart():
    assert headnotes.normalise("إثبات") == headnotes.normalise("اثبات")
    assert headnotes.normalise("الكراء") == headnotes.normalise("كراء")
    # ي and ى are different letters in these subjects and must not be merged
    assert headnotes.normalise("دعوى القسمة") != headnotes.normalise("دعوي القسمة")
    assert headnotes.normalise("كراء") != headnotes.normalise("كراء تجاري")


def test_a_bare_term_with_no_rule_is_not_taken_as_a_theme():
    """A stray phrase left on the file-number line must not become a category: with no
    sub-issue, no consequence marker and no rule behind it, nothing says it is one."""
    assert headnotes.read(
        "محكمة النقض\n"
        "الصادر بتاريخ 28/05/2019 في الملف المدني رقم 1852/1/3/2019 نزاع تحفيظ عقاري") is None


def test_petition_text_following_the_file_number_is_not_a_theme():
    """When the petition paragraph runs on from the file reference, no heading marks
    it: only its wording tells it apart. Left in, this shape alone put some 1,900
    lawyer-and-client phrases into the corpus as subjects."""
    assert headnotes.read(
        "محكمة النقض\nرقم 607/5\n"
        "الصادر بتاريخ 21/09/2021 في الملف المدني رقم 9334/1/5/2019 "
        "من طرف الطالب المذكور أعلاه - بواسطة نائبه الأستاذ (ع.د.ه) - أثره. "
        "والرامية إلى نقض قرار محكمة الاستئناف بالجديدة رقم 1104.") is None


def test_recital_heading_is_not_a_theme():
    """وبناء على الأمر بالتخلي... is the court reciting its own procedure. It carries a
    file number, and can carry dashes and a consequence marker too, so the shape alone
    does not rule it out - only knowing the heading does. Left in, وتبليغه became a
    subject on 29 rulings."""
    assert headnotes.read(
        "محكمة النقض\n"
        "وبناء على الأمر بالتخلي والإبلاغ الصادر في الملف عدد 2021/1622/3125 "
        "- وتبليغه - أثره. وبناء على الإعلام بتعيين القضية في الجلسة العلنية.") is None


def test_rule_starts_after_the_verdict_when_no_full_stop_was_printed():
    """Some headnotes carry no full stop at all. The chain still ends where the court
    recorded its verdict - (نعم) or (لا) - and the rule runs on from there. Cutting at
    a fixed width instead produced abstracts that began in the middle of a word."""
    h = headnotes.read(
        "محكمة النقض\n"
        "المؤري : 2003/10/15 الملف الشرعي عدد : 2002/1/2/66 حضانة - استقرار الزوج بالمغرب "
        "- رفض الزوجة المغربية الرجوع - حكم أجنبي - الفصل 25 من الاتفاقية القضائية (لا) "
        "- اعتماد الفصل 99 من المدونة (نعم) القضاء الأجنبي الذي أعطى حق حضانة الأولاد من "
        "أب مغربي وأم مغربية يأباه النظام العام المغربي باعتبار أن الزوجة أثناء الحياة "
        "الزوجية تكون حيث يقيم الزوج.")
    assert h.theme == "حضانة"
    assert h.rule.startswith("القضاء الأجنبي")


def test_a_stray_dot_inside_a_word_does_not_end_the_chain():
    """The OCR drops dots into the middle of words; only one with a space after it
    separates the chain from the rule."""
    h = headnotes.read(
        "محكمة النقض\n"
        "الصادر بتاريخ 11 نونبر 2020 في الملف الجنائي عدد 2019/4/6/14842 "
        "تزوير في محرر.رسمي - عدم إبراز أركانها - أثره. إن المحكمة لم تبرز الأركان.")
    assert h.theme == "تزوير في محرر.رسمي" or h.theme.startswith("تزوير")
    assert h.rule.startswith("إن المحكمة")


def test_no_rule_is_claimed_when_the_boundary_is_unknown():
    """With neither a full stop nor a verdict there is no telling where the chain ends.
    The keywords are kept, cut on a word, and no abstract is invented from the rest."""
    chain = " - ".join(["كراء", "واجبات الكراء", "إنذار بالإفراغ", "عقد كراء",
                        "كراء سكني", "كراء تجاري", "دعوى الإفراغ", "علاقة كرائية",
                        "إنذار بأداء واجبات الكراء", "تعرض الغير الخارج عن الخصومة",
                        "دعوى الطرد للاحتلال", "قوة الشيء المقضي به",
                        "عقار محفظ", "تقييد احتياطي", "مطلب تحفيظ", "نزاع تحفيظ",
                        "شفعة", "قسمة عينية", "دعوى الاستحقاق", "غرامة تهديدية",
                        "دعوى إتمام إجراءات البيع", "تعرض على مطلب تحفيظ"])
    assert len(chain) > 320
    h = headnotes.read(
        "محكمة النقض\n"
        "الصادر بتاريخ 05 أكتوبر 2021 في الملف المدني عدد 2021/4/1/4836 " + chain)
    assert h is not None
    assert h.theme == "كراء"
    assert h.rule == ""


def test_a_procedural_formula_at_the_head_is_skipped_for_the_subject():
    """The subject must be a subject. A recital or a statute reference standing first
    is passed over for the next real term rather than filed as a category."""
    h = headnotes.read(
        "محكمة النقض\n"
        "الصادر بتاريخ 05 أكتوبر 2021 في الملف المدني عدد 2021/4/1/4836 "
        "من قانون المسطرة المدنية - كراء تجاري - أثره. إن المحكمة لما قضت بذلك كانت مصيبة.")
    assert h.theme == "كراء تجاري"


def test_a_fragment_left_by_a_cut_bracket_is_not_a_subject():
    """A bracket opened or closed on its own means the line was cut through a phrase
    the court had parenthesised, leaving part of a sentence rather than a subject."""
    assert not headnotes.is_subject("حضورهما) وهو الملك المحاط بسور")
    assert not headnotes.is_subject("إجراء جوهري (لا")
    # a balanced one is how the court writes its verdict, and stays
    assert headnotes.is_subject("اعتماد الفصل 99 من المدونة (نعم)")
    assert headnotes.is_subject("واجب التمدرس")


def test_an_article_number_inside_the_headnote_is_not_mistaken_for_the_file_number():
    """Cutting at "the last number near the start" swallowed the subject whenever the
    headnote cited a statute: here the 37 of الفصل 37 won over the file number and
    everything before it went with it."""
    h = headnotes.read(
        "محكمة النقض\nالقرار رقم 536\n"
        "المؤرخ في 10 يونيو 2010 ملف إجتماعي رقم 2009/1/5/974 "
        "تبليغ – شهادة التسليم - صفة من قام بالتبليغ . بمقتضى الفصل 37 من ق.م.م.")
    assert h.theme == "تبليغ"
    assert "شهادة التسليم" in h.sub


def test_the_older_rulings_write_the_file_word_without_its_article():
    """187 rulings print "ملف شرعي عدد" and were skipped for want of the two letters."""
    h = headnotes.read(
        "محكمة النقض\nالقرار عدد 987\n"
        "الصادر بتاريخ 2000/10/18 98/1/2/321 ملف شرعي عدد "
        "التطليق للضرر – اعتماده على العنف والإهانة (نعم). القرار المنتقد في غير محله.")
    assert h is not None and h.theme == "التطليق للضرر"
