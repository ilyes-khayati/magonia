"""Checking an answer's citations against the papers that were actually retrieved.

The model is asked to cite retrieved papers by number, [1] or [1, 3]. Any number that does
not point to a retrieved paper is removed from the answer, and the removal is reported, so a
reference can never be invented. Author–year mentions that match no retrieved paper are kept
but flagged as unverified.
"""

import re
from dataclasses import dataclass, field

# [1]  [1, 3]  [2-4]  [2–4]
GROUP = re.compile(r"\s?\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
# (Sghaier et al., 2022)  (Sghaier and Dhaou 2022)  (Sghaier, 2022)
AUTHOR_YEAR = re.compile(r"\(([A-Z][A-Za-zÀ-ÿ'\-]+)[^()]*?(\d{4})[a-z]?\)")


@dataclass
class Check:
    text: str  # the answer with invalid citations removed
    cited: list[int] = field(default_factory=list)  # valid paper numbers, in order of first use
    removed: list[int] = field(default_factory=list)  # numbers that matched no retrieved paper
    unverified: list[str] = field(default_factory=list)  # author–year mentions not retrieved

    def to_dict(self) -> dict:
        return {
            "cited": self.cited,
            "removed": self.removed,
            "unverified": self.unverified,
        }


def numbers(group: str) -> list[int]:
    """The paper numbers in a citation group: "1, 3-5" gives [1, 3, 4, 5]."""
    found = []
    for part in re.split(r"\s*,\s*", group):
        ends = [int(n) for n in re.split(r"\s*[-–]\s*", part)]
        if len(ends) == 2 and 0 < ends[1] - ends[0] < 50:
            found.extend(range(ends[0], ends[1] + 1))
        else:
            found.extend(ends)
    return found


def check(answer: str, papers: list) -> Check:
    """Keep only citations to papers 1..len(papers); report what was removed or unverified."""
    result = Check(text="")

    def keep_valid(match: re.Match) -> str:
        valid = []
        for n in numbers(match.group(1)):
            if 1 <= n <= len(papers):
                valid.append(n)
                if n not in result.cited:
                    result.cited.append(n)
            elif n not in result.removed:
                result.removed.append(n)
        if not valid:
            return ""
        spacer = " " if match.group(0).startswith(" ") else ""
        return f"{spacer}[{', '.join(str(n) for n in valid)}]"

    result.text = GROUP.sub(keep_valid, answer)

    known = {(p.authors[0].split()[-1].lower(), p.year) for p in papers if p.authors}
    for match in AUTHOR_YEAR.finditer(result.text):
        surname, year = match.group(1).lower(), int(match.group(2))
        if (surname, year) not in known:
            result.unverified.append(match.group(0))
    return result
