"""The checks that decide whether a French file is shipped.

A translation is only written if it is whole. These are the ways it can fail to be,
each of which would otherwise reach a court as a finished document.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import deliver


def test_a_translation_that_drops_a_redaction_is_not_shipped():
    """Every XXXXXXX is a name the anonymizer removed. Losing one leaves a sentence
    reading as if nobody had been named -- a free translator did that to 4 of 44."""
    src = "حكم على XXXXXXX لفائدة XXXXXXX"
    assert deliver.whole(src, "condamné XXXXXXX au profit de M. Alami") != ""
    assert deliver.whole(src, "condamné XXXXXXX au profit de XXXXXXX") == ""


def test_a_translation_cut_short_is_not_shipped():
    src = "ا" * 1000
    assert "too short" in deliver.whole(src, "b" * 300)
    assert deliver.whole(src, "b" * 900) == ""


def test_an_empty_answer_is_not_shipped():
    assert deliver.whole("نص", "   ") == "empty"


def test_the_abstract_and_the_ruling_are_told_apart_after_translation():
    got = deliver.split_answer("Le résumé.\n####\nLe texte.\nSuite.", had_abstract=True)
    assert got == ("Le résumé.", "Le texte.\nSuite.")


def test_a_lost_or_doubled_separator_is_a_failure_not_a_guess():
    """Guessing where the abstract ended would put half a ruling in bold."""
    assert deliver.split_answer("Le résumé.\nLe texte.", had_abstract=True) is None
    assert deliver.split_answer("a\n####\nb\n####\nc", had_abstract=True) is None


def test_a_ruling_without_an_abstract_needs_no_separator():
    assert deliver.split_answer("Le texte.", had_abstract=False) == ("", "Le texte.")


def test_the_abstract_rides_with_the_first_piece_only():
    long_body = "\n".join(["سطر " * 40] * 400)          # well over one piece
    ps = deliver.pieces("الملخص", long_body)
    assert len(ps) > 1
    assert ps[0].startswith("الملخص\n####\n")
    assert all("####" not in p for p in ps[1:])


def test_each_redaction_is_numbered_and_must_come_back_once():
    src, n = deliver.protect("XXXXXXX و XXXXXXX و XXXXXXX")
    assert n == 3 and src == "§1§ و §2§ و §3§"
    assert deliver.restore("§1§ et §2§ et §3§", 3) == "XXXXXXX et XXXXXXX et XXXXXXX"


def test_a_dropped_or_repeated_redaction_is_caught():
    assert deliver.restore("§1§ et §3§", 3) is None          # one dropped
    assert deliver.restore("§1§ §2§ §2§ §3§", 3) is None     # one repeated
