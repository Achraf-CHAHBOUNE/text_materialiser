"""Arabic text normalization + tolerant search (website_brief §S-5/§S-6).

A search must return the same results whether the user types أ or ا, ي or ى, with or
without diacritics or tatweel, and with Arabic-Indic or ASCII digits. We achieve that by
normalizing both the indexed text and the query the same way, and by building a
diacritic-tolerant regex to highlight *why* a result matched in the original text.
"""
from __future__ import annotations

import re
from typing import List

# Diacritics (harakat) + tatweel — explicit code points.
_DIAC = re.compile("[ؐ-ؚـً-ٰٟ]")
_DIAC_OPT = "[ؐ-ًؚ-ٰٟ]*"  # optional diacritics between letters (no tatweel here)
_AR2ASCII = {ord("٠") + i: str(i) for i in range(10)}  # Arabic-Indic digits -> ASCII
_ALEF = "اأإآٱ"
_YA = "يى"
_TA = "ةه"   # taa marbuta / haa — matched as equivalent (mirrors normalize())


def normalize(s: str) -> str:
    """Canonical form for indexing and comparing (variant-insensitive)."""
    s = (s or "").translate(_AR2ASCII)
    s = _DIAC.sub("", s)
    for a in "أإآٱ":
        s = s.replace(a, "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = s.lower()
    return re.sub(r"\s+", " ", s).strip()


# Arabic attaches letters to the front of a word, so a word index files التعويض and
# بالتعويض as tokens unrelated to تعويض, and a search for one finds none of the others.
# The query is widened to cover them -- but only by the article, and that limit is
# measured, not a matter of taste: at two variants Postgres uses the word index and a
# search costs 40 ms; add بال and وال and it stops trusting the index, falls back to
# reading every ruling, and the same search costs a second. Those two extra forms are
# worth 5% more results and 25 times the work, so the article alone is where this stops.
# Rarer forms are still reachable: a query that finds nothing falls back to substring
# matching over the trigram index (see db._text_match).
_PREFIXES = ("", "ال")
_WORD = re.compile(r"[^\w؀-ۿ]+")


def prefix_variants(term: str) -> List[str]:
    """`term` and the same word carrying each Arabic prefix.

    Used to widen a word-index query so that searching تعويض also finds التعويض and
    بالتعويض, which are separate tokens to any word index. Returns nothing for a term
    too short to be worth it, where a prefix would be most of the word.
    """
    term = _WORD.sub("", normalize(term))
    if len(term) < 3:
        return []
    return [p + term for p in _PREFIXES]


def tsquery(query: str) -> str:
    """A Postgres tsquery for `query`: every word, each widened by its prefixes.

    Words are ANDed, variants ORed, and every variant is a prefix match so that
    suffixed forms (تعويضات) come back too. Only letters and digits survive
    normalization, so nothing the user types can reach the parser as syntax.
    """
    groups = []
    for word in normalize(query).split():
        variants = prefix_variants(word)
        if variants:
            groups.append("(" + " | ".join(v + ":*" for v in variants) + ")")
    return " & ".join(groups)


def _char_class(ch: str) -> str:
    if ch in _ALEF:
        return f"[{_ALEF}]"
    if ch in _YA:
        return f"[{_YA}]"
    if ch in _TA:
        return f"[{_TA}]"
    return re.escape(ch)


def make_regex(query: str) -> re.Pattern | None:
    """Diacritic/variant-tolerant regex matching `query` inside ORIGINAL text."""
    q = (query or "").translate(_AR2ASCII).strip()
    q = _DIAC.sub("", q)
    tokens = [t for t in q.split() if t]
    if not tokens:
        return None
    parts = []
    for tok in tokens:
        parts.append(_DIAC_OPT.join(_char_class(c) for c in tok))
    pattern = r"\s+".join(parts)
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def matches(text: str, query: str) -> bool:
    """True if the normalized query occurs in the normalized text."""
    nq = normalize(query)
    return bool(nq) and nq in normalize(text)


def snippets(text: str, query: str, width: int = 60, limit: int = 3) -> List[str]:
    """Return up to `limit` snippets around matches, with the hit wrapped in «…»
    markers the frontend renders as highlights. Falls back to [] if no match."""
    rx = make_regex(query)
    if not rx:
        return []
    out: List[str] = []
    for m in rx.finditer(text):
        start = max(0, m.start() - width)
        end = min(len(text), m.end() + width)
        pre = ("…" if start > 0 else "") + text[start:m.start()]
        hit = text[m.start():m.end()]
        post = text[m.end():end] + ("…" if end < len(text) else "")
        out.append(f"{pre}«{hit}»{post}".replace("\n", " ").strip())
        if len(out) >= limit:
            break
    return out
