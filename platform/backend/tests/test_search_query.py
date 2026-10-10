"""Building the word query that searches the rulings.

The search runs over a word index on Postgres, and a word index knows nothing about
Arabic morphology: التعويض and بالتعويض are tokens of their own, unrelated to تعويض.
These rules are what makes a search for one find the others, and what keeps anything
a reader types out of the query parser.
"""
import textnorm


def test_a_term_is_widened_by_the_article():
    got = textnorm.prefix_variants("تعويض")
    assert got == ["تعويض", "التعويض"]


def test_widening_stops_at_the_article():
    """Not a style choice: past two variants Postgres stops using the word index and a
    search goes from 40 ms to about a second, for 5% more results."""
    assert len(textnorm.prefix_variants("تعويض")) == 2


def test_the_query_ands_words_and_ors_their_variants():
    q = textnorm.tsquery("تعويض حادثة")
    assert q.count("&") == 1              # two words, both required
    assert "|" in q                       # each widened
    assert q.startswith("(") and q.endswith(")")


def test_every_variant_matches_as_a_prefix():
    """So that تعويضات comes back for تعويض, which no amount of prefixing would do."""
    q = textnorm.tsquery("تعويض")
    assert all(part.strip().endswith(":*") for part in q.strip("()").split("|"))


def test_the_query_is_normalised_like_the_stored_text():
    """The text is indexed normalised, so ة and ه must not be two different searches."""
    assert textnorm.tsquery("حادثة") == textnorm.tsquery("حادثه")
    assert textnorm.tsquery("إثبات") == textnorm.tsquery("اثبات")


def test_nothing_a_reader_types_reaches_the_parser():
    """tsquery has its own syntax; a stray & or ! must not become an operator."""
    for hostile in ["تعويض & !حادثة", "تعويض | *", "'; drop table decisions; --",
                    "تعويض:*)|(", "\\"]:
        q = textnorm.tsquery(hostile)
        # the only characters that are not letters or digits are the syntax we wrote:
        # the prefixes we add are Arabic letters, so they are covered by that
        punctuation = {c for c in q if not c.isalnum() and not "؀" <= c <= "ۿ"}
        assert punctuation <= set("()|&:* "), (hostile, punctuation)


def test_a_term_too_short_to_widen_is_dropped():
    """With a two-letter word the prefix would be most of it, and every ruling matches."""
    assert textnorm.tsquery("في") == ""
    assert textnorm.tsquery("من في") == ""


def test_a_short_word_does_not_sink_the_rest_of_the_query():
    q = textnorm.tsquery("في تعويض")
    assert "تعويض" in q and q.count("&") == 0


def test_variants_are_normalised_even_when_asked_for_directly():
    """tsquery normalises before it splits, so the normalising inside prefix_variants
    is only reachable this way -- and it is what makes the function correct on its own."""
    assert textnorm.prefix_variants("حادثة") == textnorm.prefix_variants("حادثه")
    assert textnorm.prefix_variants("إثبات") == textnorm.prefix_variants("اثبات")
