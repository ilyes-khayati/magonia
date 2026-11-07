"""Checking an answer's citations against the papers that were actually retrieved.

The model is asked to cite retrieved papers by number, [1] or [1, 3]. Any number that does
not point to a retrieved paper is removed from the answer, and the removal is reported, so a
reference can never be invented. When it read passages of a paper's full text, it may cite a
page, [1, p. 6]; the page is kept only if a passage from that page was given to it. Author–year mentions that match no retrieved paper are kept
but flagged as unverified.
"""

import re
from dataclasses import dataclass, field

# [1]  [1, 3]  [2-4]  [2–4]  [1, p. 6]  [1 p.6]  [1, pp. 6-7]
GROUP = re.compile(r"\s?\[(\d+(?:\s*[-–,]\s*\d+)*?)(?:,?\s*pp?\.\s*(\d+)(?:\s*[-–]\s*\d+)?)?\]")
# (Sghaier et al., 2022)  (Sghaier and Dhaou 2022)  (Sghaier, 2022)
AUTHOR_YEAR = re.compile(r"\(([A-Z][A-Za-zÀ-ÿ'\-]+)[^()]*?(\d{4})[a-z]?\)")


@dataclass
class Check:
    text: str  # the answer with invalid citations removed
    cited: list[int] = field(default_factory=list)  # valid paper numbers, in order of first use
    removed: list[int] = field(default_factory=list)  # numbers that matched no retrieved paper
    unverified: list[str] = field(default_factory=list)  # author–year mentions not retrieved
    pages_removed: list[str] = field(default_factory=list)  # pages no passage came from

    def to_dict(self) -> dict:
        return {
            "cited": self.cited,
            "removed": self.removed,
            "unverified": self.unverified,
            "pages_removed": self.pages_removed,
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


# A first sentence that only announces the answer: "Based on the literature, here is what is
# known about…:". It carries nothing, and the support check counts it as a claim.
FRAMING = re.compile(
    r"^\s*(based on (the )?(literature|studies|research|papers|sources|the papers found)[^.\n]*|"
    r"here (is|are) (what|some|a summary)[^.\n]*|"
    r"(the )?(literature|research|studies) (suggests?|shows?|indicates?) the following[^.\n]*)"
    r"[:.]\s*\n*",
    re.IGNORECASE,
)


def without_framing(answer: str) -> str:
    """The answer without an opening sentence that only announces it."""
    match = FRAMING.match(answer)
    return answer[match.end() :] if match and match.end() < 220 else answer


# a sentence, whose full stops after "et al", "e.g", "p" or in a number do not end it
ABBREVIATION = "".join(
    rf"|(?<=\b{a})\." for a in ("al", "e", "g", "i", "p", "pp", "vs", "Fig", "fig")
)
SENTENCE = re.compile(rf"(?:[^.!?\n]|\.(?=\d){ABBREVIATION})+(?:[.!?]|$)")


def by_name(answer: str, papers: list) -> str:
    """A sentence that names a paper found ("Sghaier et al., 2022 assessed…", "as Sghaier et
    al. (2022) found") but cites no number gets that paper's number, so that its support is
    checked like any cited sentence. Measured: a small model often names a paper instead of
    citing it, and those sentences went unchecked."""
    names = {}
    for n, p in enumerate(papers, start=1):
        if p.authors:
            names.setdefault((p.authors[0].split()[-1].lower(), p.year), n)
    surnames = [s for s, _ in names]

    def cite(match: re.Match) -> str:
        sentence = match.group(0)
        if GROUP.search(sentence):
            return sentence
        found = []
        for (surname, year), n in names.items():
            named = re.search(rf"\b{re.escape(surname)}\b", sentence, re.IGNORECASE)
            # the year must be there too, unless no other paper has that first author
            if named and (str(year) in sentence or surnames.count(surname) == 1):
                found.append(n)
        if not found:
            return sentence
        end = re.search(r"[.!?]?\s*$", sentence)
        return f"{sentence[: end.start()]} [{', '.join(map(str, sorted(found)))}]{sentence[end.start() :]}"

    return SENTENCE.sub(cite, answer)


def check(answer: str, papers: list, pages: dict[int, set[int]] | None = None) -> Check:
    """Keep only citations to papers 1..len(papers), and pages a passage came from (pages
    maps a paper's number to the pages given); report what was removed or unverified."""
    result = Check(text="")
    answer = by_name(without_framing(answer), papers)

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
        cited = ", ".join(str(n) for n in valid)
        page = match.group(2)
        if page and len(valid) == 1:
            if int(page) in (pages or {}).get(valid[0], set()):
                return f"{spacer}[{cited}, p. {page}]"
            result.pages_removed.append(f"[{cited}, p. {page}]")
        return f"{spacer}[{cited}]"

    result.text = GROUP.sub(keep_valid, answer)

    known = {(p.authors[0].split()[-1].lower(), p.year) for p in papers if p.authors}
    for match in AUTHOR_YEAR.finditer(result.text):
        surname, year = match.group(1).lower(), int(match.group(2))
        if (surname, year) not in known:
            result.unverified.append(match.group(0))
    return result
