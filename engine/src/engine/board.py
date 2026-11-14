"""The researcher's board as memory Magon can cite.

What the researcher pins is what they chose to keep: findings computed in the workspace,
earlier answers, passages of papers and their own notes. Magon is given these as numbered
evidence, cited [B1], [B2]… like papers, each with how far it can be trusted:

- computed: a card or experiment computed in this workspace from the researcher's data
- checked: an earlier answer whose checks passed
- passage: a paper's words, pinned by the researcher
- note: the researcher's own words, to be quoted as theirs and never stated as a finding

An earlier answer whose checks failed is never given as evidence. When the board holds more
than fits the prompt, the items closest to the question are given.
"""

import re
from dataclasses import dataclass

from engine.literature import keywords

TRUST = {
    "computed": "computed in this workspace",
    "checked": "an earlier answer whose checks passed",
    "passage": "a passage of a paper, in its words",
    "note": "the researcher's own note: quote it as theirs, never as a finding",
}
MAX_GIVEN = 8  # board items given with one question
CITE = re.compile(r"\s?\[B(\d+)\]")

RULES = (
    "The board items above are what the researcher pinned. Where one answers the question, "
    "use it and cite it as [B1], [B2]…, as you cite papers. A note is the researcher's own "
    "words: say so (for example 'your note says…') and do not present it as a finding. Do "
    "not cite a board item for something it does not say."
)


@dataclass
class Pinned:
    title: str
    text: str
    trust: str  # computed, checked, passage, note, or failed
    pinned: str = ""  # the date it was pinned
    n: int = 0  # its number among the items given, set by given()

    def to_dict(self) -> dict:
        return {"n": self.n, "title": self.title, "trust": self.trust, "pinned": self.pinned}


def given(board: list[Pinned], question: str, limit: int = MAX_GIVEN) -> list[Pinned]:
    """The items given with a question, numbered from 1, in board order."""
    usable = [b for b in board if b.trust in TRUST and b.text.strip()]
    if len(usable) > limit:
        def words(t: str) -> set[str]:
            return {w.lower() for w in keywords(t, most=500).split()}

        asked = words(question)

        def overlap(b: Pinned) -> int:
            return len(asked & words(f"{b.title} {b.text}"))

        keep = sorted(range(len(usable)), key=lambda i: (-overlap(usable[i]), i))[:limit]
        usable = [usable[i] for i in sorted(keep)]
    return [Pinned(b.title, b.text, b.trust, b.pinned, n) for n, b in enumerate(usable, start=1)]


def block(items: list[Pinned]) -> str:
    """The board items as the model reads them."""
    lines = ["From the researcher's board:"]
    for b in items:
        date = f", pinned {b.pinned[:10]}" if b.pinned else ""
        lines.append(f"[B{b.n}] {b.title} ({TRUST[b.trust]}{date}): {b.text[:1500]}")
    return "\n".join(lines) + "\n\n" + RULES


def check(answer: str, items: list[Pinned]) -> tuple[str, list[int], list[int]]:
    """Keep only citations to the board items given; report those cited and those removed."""
    cited, removed = [], []

    def keep(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= len(items):
            if n not in cited:
                cited.append(n)
            return match.group(0)
        if n not in removed:
            removed.append(n)
        return ""

    return CITE.sub(keep, answer), cited, removed
