"""Checking the numbers in an answer against what the model was given.

The model is told to copy numbers from the facts about the researcher's data, from the
readings it took and from the papers it found. After the answer is written, every number in
it is looked for in those sources. A number found there is verified and linked to where it
came from; one found only with the opposite sign is flagged; one found nowhere is flagged as
not given. The model cannot make a number look checked.
"""

import re
from dataclasses import asdict, dataclass

from engine.citations import GROUP

# 0.89  -0.15  +0.003  24.1  50%  2022   (a minus may be written as − or -)
NUMBER = re.compile(r"(?<![\w.])(?P<sign>[-+−])?(?P<digits>\d+(?:\.\d+)?)(?![\w])")
DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")  # 2022-07: a date, not a measurement
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


def value_of(match: re.Match) -> Found:
    digits = match["digits"]
    sign = -1 if match["sign"] in ("-", "−") else 1
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    return Found(sign * float(digits), decimals)


def skipped(text: str) -> list[tuple[int, int]]:
    """Spans that hold numbers which are not measurements: dates, citations, list numbering."""
    spans = [m.span() for m in DATE.finditer(text)]
    spans += [m.span() for m in GROUP.finditer(text)]
    spans += [m.span() for m in LIST_MARKER.finditer(text)]
    return spans


def numbers_in(text: str) -> list[tuple[re.Match, Found]]:
    spans = skipped(text)
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


def check_numbers(answer: str, sources: list[tuple[str, str]]) -> list[Number]:
    """Every number in the answer, with where it was found among the (label, text) sources."""
    given = [(label, found) for label, text in sources for _, found in numbers_in(text)]
    checked = []
    for match, written in numbers_in(answer):
        text = answer[match.start() : match.end()]
        if source := best_source(written, given):
            checked.append(Number(match.start(), match.end(), text, "verified", source))
            continue
        source = best_source(Found(-written.value, written.decimals), given)
        status = "sign" if source and written.value != 0 else "unverified"
        checked.append(Number(match.start(), match.end(), text, status, source))
    return checked
