"""Read a ruling's own headnote: the subject it is filed under, and the legal rule.

Moroccan Cassation rulings print, right after the file-number line, a headnote in a
fixed shape:

    <theme> - <sub-issue> - <sub-issue> - <أثره>.  <the legal rule, one paragraph>

for example

    جناية التزوير في محرر رسمي - عدم إبراز أركانها - أثره. إن المحكمة لم تبرز أركان...

The first term is the subject the court itself files the ruling under, the middle terms
narrow it down, the last is a fixed consequence marker (أثره / حجيته / نعم / ...), and
the sentence after the full stop is the rule - what the Cassation portal calls القاعدة
and what a reader wants as the abstract.

Taking the subject from the page rather than inventing one matters: the portal's own
search form offers no list of مواضيع to borrow, only a free-text box over this very
line, so the court's wording is the only authority there is.

Three things make the line hard to cut:

  - the file number sits before "في الملف" about as often as after it, because the PDFs
    lose right-to-left order, and the word after it is sometimes glued to the number
    (المدني1852/1/3/2019);
  - the petition paragraph ("... من طرف الطالب المذكور بواسطة نائبه الأستاذ ...") also
    mentions a file number, so it reads like a headnote unless ruled out by name;
  - the court decorates headings with tatweel (باسـم جلالــة الملــك), so a heading has
    to be matched on its letters rather than on its bytes.

About half the corpus carries no headnote at all - the civil chamber usually prints the
file-number line and goes straight to باسم جلالة الملك - so `read` returning None is the
normal answer for those, not a failure.
"""
from __future__ import annotations

import re
from typing import NamedTuple

AR = r"؀-ۿ"
# the OCR reads الملف as المحلف or الملقف often enough to be worth naming
FILE_WORD = r"(?:الملف|المحلف|الملقف)"
FILE_PHRASE = re.compile(rf"(?:في\s+)?{FILE_WORD}\s*[{AR}]*\s*(?:رقم|عدد|عـدد)?\s*[:\s]*")
NUMS = re.compile(r"\d[\d\s/\-.]*\d|\d")
DASH = re.compile(r"\s*[-–—]\s*|\s+[-–—]|[-–—]\s+")
BANNER = re.compile(r"نشرة قرارات محكمة النقض[^\n]*?العدد\s*\d+\s*")
MARKS = re.compile(r"[ـً-ْٰ‏‎]")   # tatweel, harakat, bidi

# the fixed markers a headnote chain ends with: a consequence, not a subject
QUALIFIERS = {
    "أثره", "أثرها", "أثره القانوني", "لا أثر له", "نعم", "لا",
    "حجيته", "حجيتها", "مشروعيته", "مشروعيتها", "شروطه", "شروطها", "مبرراته",
    "مبرراتها", "صحته", "صحتها", "جوازه", "عدم جوازه", "سلطة المحكمة",
    "عناصره التكوينية", "عناصرها التكوينية", "عناصر التقدير", "كسرا", "تعليله",
    "نطاقه", "حدوده", "مداه", "خرق للقانون", "لا يعد كذلك", "يعد كذلك", "جزاؤه",
}
# headings and running text that are not a headnote, matched on the letters alone
JUNK = re.compile(
    r"^(?:وبناء على|بناء على|حيث|باسم جلالة|المملكة المغربية|المجلس الأعلى|محكمة النقض|"
    r"قرار محكمة النقض|عن محكمة الاستئناف|لهذه الأسباب|قضت محكمة|في الشكل|في الوسيلة|"
    r"في شأن|رفض الطلب|نقض و|تسجيل التنازل|بعد أن تل|إن محكمة النقض|وبعد المداولة|"
    r"المبيعة موضوع|في الموضوع)")
# wording that only ever belongs to the petition paragraph, wherever it appears
PETITION = re.compile(
    r"من طرف|بواسطة|نائب|الأستاذ|الرامي|بمقتضى|المذكور|أفضى|المرفوع|المودعة|العريضة|"
    r"المداولة|يستفاد|المطعون فيه|أوراق الملف|وثائق الملف|الأوراق الأخرى|المدلى بها|"
    r"^وبناء على|^بناء على|^من القانون|^من الفصل|^من ق\b|^الفصل|^المادة")
STOP = {"من ق", "في", "من", "على", "عن", "وفي", "ثم", "أي", "به", "لها", "له"}

# A full stop ends the chain only when a space follows it: the OCR leaves stray dots
# inside words. When the court printed no full stop at all, the chain still ends with
# its parenthesised verdict - (نعم) or (لا) - and the rule runs on from there.
SENTENCE_END = re.compile(r"\.(?=\s|$)")
VERDICT = re.compile(r"\((?:نعم|لا)\)")
CHAIN_MAX = 320

# A theme is a noun phrase naming a subject. Two shapes never are one: a procedural
# formula the court recites (وبناء على الأمر بالتخلي...، وبعد تلاوة المستشار...), which
# runs on from the line above, and a dangling reference to a statute or an amount.
# Matching the openers rather than the leading waw keeps the real subjects that begin
# with one: واجبات الكراء، وسيلة النقض، وعد بالبيع، وصية. وتبليغ needs its waw to be
# rejected, because تبليغ on its own is a subject - service of process.
FORMULA = re.compile(r"^و?\s?(?:بناء|بعد|برفض|بمقتضى|حيث)|^وتبليغ|^استنادا")
REFERENCE = re.compile(r"^من\s|^من[قم]$|^درهم|^بتاريخ|^الفصل|^المادة|^الظهير")


def is_subject(term: str) -> bool:
    """Whether a term can stand as the subject a ruling is filed under.

    A bracket left open or closed on its own means the line was cut through a phrase
    the court had parenthesised, so what survives is a fragment of a sentence rather
    than a subject: "حضورهما) وهو الملك المحاط بسور". Length and a leading waw look
    like the same thing but are not - واجب التمدرس and الاتجار في المخدرات والحيازة
    غير المبررة للمخدرات are both real subjects.
    """
    return (len(term) <= 60 and term.count("(") == term.count(")")
            and not FORMULA.match(term) and not REFERENCE.match(term))


def _split_chain(rest: str) -> tuple:
    """Split the headnote into its keyword chain and its rule.

    With neither a full stop nor a verdict marker there is no telling where the chain
    ends, so the whole line is kept as keywords and no rule is claimed. An abstract
    that starts mid-word reads as damage; having none is merely honest.
    """
    m = SENTENCE_END.search(rest)
    if m and m.start() <= CHAIN_MAX:
        return rest[:m.start()], rest[m.end():]
    last = None
    for last in VERDICT.finditer(rest[:CHAIN_MAX]):
        pass
    if last:
        return rest[:last.end()], rest[last.end():]
    if len(rest) <= CHAIN_MAX:
        return rest, ""
    cut = rest.rfind(" ", 0, CHAIN_MAX)        # never cut a word in half
    return rest[:cut if cut > 0 else CHAIN_MAX], ""


class Headnote(NamedTuple):
    theme: str            # the subject the ruling is filed under
    sub: list             # the sub-issues that narrow it down
    qualifier: str        # the consequence marker the chain ends with, if any
    rule: str             # the legal rule: the abstract, in the court's words


def normalise(theme: str) -> str:
    """A grouping key: one alef, no marks, no leading article.

    Rulings spell the same subject several ways (إثبات / اثبات, كراء / الكراء), so
    counting or looking up a theme has to happen on a key rather than on the surface
    form. The form the court used most often stays the label.
    """
    t = MARKS.sub("", theme)
    t = re.sub(r"[أإآٱ]", "ا", t)
    t = re.sub(r"^ال(?=[^\s]{3})", "", t)
    return re.sub(r"\s+", " ", t).strip()


_QUAL_KEYS = {normalise(q) for q in QUALIFIERS}


def _clean(term: str) -> str:
    term = re.sub(rf"[^{AR}\s()،]", " ", term)           # drop digits and latin
    return re.sub(r"\s+", " ", term).strip(" .:،؛()‏‎")


def read(text: str) -> Headnote | None:
    """Return the ruling's headnote, or None when it does not print one."""
    lines = [l for l in (BANNER.sub("", l).strip() for l in text.split("\n")) if l]
    for raw in lines[:12]:
        line = MARKS.sub("", raw)
        if not re.search(FILE_WORD, line) or JUNK.match(line):
            continue
        rest = FILE_PHRASE.sub(" ", line, count=1)
        # cut the date and file number: everything up to the last number near the start
        last = None
        for m in NUMS.finditer(rest):
            if m.start() > 110:
                break
            last = m
        if last:
            rest = rest[last.end():]
        rest = rest.strip(" .:،؛/")
        if len(rest) < 8:
            continue

        chain, rule = _split_chain(rest)
        terms = [_clean(p) for p in DASH.split(chain)]
        terms = [t for t in terms if 3 <= len(t) <= 110 and t not in STOP]
        # the petition paragraph often runs on from the headnote on the same line, so
        # drop the terms that belong to it rather than throwing the whole line away
        terms = [t for t in terms if not PETITION.search(t)]
        if not terms:
            continue

        qualifier = terms[-1] if normalise(terms[-1]) in _QUAL_KEYS else ""
        if qualifier:
            terms = terms[:-1]
        # The theme has to be a subject. The terms after it need not be: a statute or
        # an amount is a real part of the chain the portal prints, just not a category.
        while terms and not is_subject(terms[0]):
            terms = terms[1:]
        if not terms:
            continue
        # a bare theme with no qualifier and no rule is probably a bad cut
        if len(terms) == 1 and not qualifier and len(rule.strip()) < 60:
            continue
        return Headnote(terms[0], terms[1:], qualifier, rule.strip())
    return None
