"""Checking the numbers in an answer against what the model was given.

The model is told to copy numbers from the facts about the researcher's data, from the
readings it took and from the papers it found. After the answer is written, every number in
it is looked for in those sources. A number found there is verified and linked to where it
came from; one found only with the opposite sign is flagged; one found nowhere is flagged as
not given. The model cannot make a number look checked.

A number must also be found where the sentence points. Finding 0.23 somewhere in 25 years of
readings is not enough when the sentence says "NDVI goes as low as 0.23 in July" of the
average year and 0.23 is July of 2002. So each number given is kept with what it is about:
the variables its source names, the year it belongs to, the month or year written just before
it ("Jul 0.23", "2002 0.40"). A written number is verified only by a given one whose
variables, year and month agree with what its sentence names (or, for the year, the question
and the rest of the answer). Found only elsewhere, it is flagged as taken from elsewhere.
"""

import re
from dataclasses import asdict, dataclass

from engine.catalogue import CATALOGUE
from engine.citations import GROUP

# 0.89  -0.15  +0.003  24.1  50%  2022   (a minus may be written as − or -)
NUMBER = re.compile(r"(?<![\w.])(?P<sign>[-+−])?(?P<digits>\d+(?:\.\d+)?)(?![\w])")
DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")  # 2022-07: a date, not a measurement
# a year names a time, not a measurement: marking it as checked would only add noise
YEAR = re.compile(r"(?<![\w.\-−+])(19[5-9]\d|20\d\d)(?![\w.%]|\.\d)")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH = re.compile(r"\b(" + "|".join(MONTHS) + r")[a-z]*\b", re.IGNORECASE)
# how each variable may be named, in a sentence or a source
VARIABLE_WORDS = {
    key: {key.replace("_", " "), v.name.lower()} | ({"lst"} if key == "lst" else set())
    for key, v in CATALOGUE.items()
}
SOURCE_YEAR = re.compile(r"\bin (19[5-9]\d|20\d\d)\b")
LABEL_YEAR = re.compile(r"\b(19[5-9]\d|20\d\d)$")
KEY_BEFORE = re.compile(
    r"(?:\b(?P<month>" + "|".join(MONTHS) + r")[a-z]*|\b(?P<year>19[5-9]\d|20\d\d))[ :(]*$",
    re.IGNORECASE,
)
LIST_MARKER = re.compile(r"^[ \t#>*-]*\d+[.)][ \t]", re.MULTILINE)  # "1. " at a line start


@dataclass
class Number:
    start: int  # position in the answer text
    end: int
    text: str
    status: str  # verified, sign (found only with the other sign), or unverified
    source: str | None = None  # where a verified number was found, e.g. "NDVI chart"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Found:
    value: float
    decimals: int
    # what the number is about, for given numbers: variables of its source, its year, and
    # the month or year written just before it
    variables: frozenset = frozenset()
    year: str | None = None
    month: str | None = None


def variables_in(text: str) -> frozenset:
    low = text.lower()
    return frozenset(
        k
        for k, words in VARIABLE_WORDS.items()
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words)
    )


def months_in(text: str) -> set[str]:
    return {m.group(1).lower()[:3] for m in MONTH.finditer(text)}


def years_in(text: str) -> set[str]:
    return set(YEAR.findall(text))


def key_before(text: str, at: int) -> tuple[str | None, str | None]:
    """The month or year written right before a number, as in "Jul 0.23" or "2002 0.40";
    only when nothing but a space, a colon or a bracket stands between them."""
    before = text[max(0, at - 14) : at]
    key = KEY_BEFORE.search(before)
    if not key:
        return None, None
    if key.group("year"):
        return key.group("year"), None
    return None, key.group("month").lower()[:3]


def value_of(match: re.Match) -> Found:
    digits = match["digits"]
    sign = -1 if match["sign"] in ("-", "−") else 1
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    return Found(sign * float(digits), decimals)


def skipped(text: str) -> list[tuple[int, int]]:
    """Spans that hold numbers which are not measurements: dates, years, citations, list
    numbering."""
    spans = [m.span() for m in DATE.finditer(text)]
    spans += [m.span() for m in YEAR.finditer(text)]
    spans += [m.span() for m in GROUP.finditer(text)]
    spans += [m.span() for m in LIST_MARKER.finditer(text)]
    return spans


def named(text: str, labels: list[str]) -> list[tuple[int, int]]:
    """Where the answer names a card it was given ("Models 4", "Paper method 1: NDVI forecast"):
    the digits in a name are part of the name, not a measurement."""
    names = {part for label in labels for part in (label, label.split(":")[0]) if len(part) > 3}
    return [
        m.span()
        for name in sorted(names, key=len, reverse=True)
        for m in re.finditer(re.escape(name), text)
    ]


def numbers_in(text: str, labels: list[str] | None = None) -> list[tuple[re.Match, Found]]:
    spans = skipped(text) + named(text, labels or [])
    return [
        (m, value_of(m))
        for m in NUMBER.finditer(text)
        if not any(start <= m.start() < end for start, end in spans)
    ]


def matches(written: Found, given: Found) -> bool:
    """The same number, or the given one rounded to as many decimals as were written."""
    if written.decimals > given.decimals:
        return False
    return abs(round(given.value, written.decimals) - written.value) < 1e-9


def best_source(written: Found, given: list[tuple[str, Found]]) -> str | None:
    """Where the number most likely came from: an exact copy before a rounding, the closest
    value, and among equals the source given last (a reading taken for this answer)."""
    candidates = [
        (g.decimals != written.decimals, abs(g.value - written.value), -i, label)
        for i, (label, g) in enumerate(given)
        if matches(written, g)
    ]
    return min(candidates)[3] if candidates else None


def given_numbers(sources: list[tuple[str, str]]) -> list[tuple[str, Found]]:
    """Every number in the sources, with what it is about."""
    given = []
    for label, text in sources:
        variables = variables_in(f"{label} {text}")
        # a source about one year: a reading "monthly means in 2002", or a label ending in it
        own = SOURCE_YEAR.findall(text) + LABEL_YEAR.findall(label)
        source_year = own[0] if len(set(own)) == 1 else None
        for match, found in numbers_in(text):
            year, month = key_before(text, match.start())
            found.variables = variables
            found.year = year or source_year
            found.month = month
            given.append((label, found))
    return given


def sentence_at(text: str, at: int) -> str:
    start = max(text.rfind(". ", 0, at), text.rfind("\n", 0, at)) + 1
    ends = [i for i in (text.find(". ", at), text.find("\n", at)) if i != -1]
    return text[start : min(ends) if ends else len(text)]


def anchored(written: Found, sentence: str, years: set[str], question: str = ""):
    """Whether a given number is about what the sentence names; a sentence that names no
    variable is about the variables of the question."""
    named_variables = variables_in(sentence) or variables_in(question)
    named_months = months_in(sentence)

    def fits(g: Found) -> bool:
        if named_variables and g.variables and not (named_variables & g.variables):
            return False
        if g.year and g.year not in years:
            return False
        return not (named_months and g.month and g.month not in named_months)

    return fits


def check_numbers(answer: str, sources: list[tuple[str, str]]) -> list[Number]:
    """Every number in the answer, with where it was found among the (label, text) sources."""
    given = given_numbers(sources)
    # a year counts as named when the sentence, the rest of the answer or the question names it
    question = " ".join(text for label, text in sources if label == "your question")
    checked = []
    for match, written in numbers_in(answer, [label for label, _ in sources]):
        text = answer[match.start() : match.end()]
        sentence = sentence_at(answer, match.start())
        fits = anchored(written, sentence, years_in(answer) | years_in(question), question)
        here = [(label, g) for label, g in given if fits(g)]
        if source := best_source(written, here):
            checked.append(Number(match.start(), match.end(), text, "verified", source))
            continue
        # found, but not where the sentence points: named after its likeliest source, one
        # about the same variable when there is one
        named = variables_in(sentence) or variables_in(question)
        same = [(label, g) for label, g in given if not named or named & g.variables]
        if source := best_source(written, same) or best_source(written, given):
            checked.append(Number(match.start(), match.end(), text, "elsewhere", source))
            continue
        source = best_source(Found(-written.value, written.decimals), here)
        status = "sign" if source and written.value != 0 else "unverified"
        checked.append(Number(match.start(), match.end(), text, status, source))
    return checked
