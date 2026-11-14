"""Checking that each statement of an answer is supported by the paper it cites.

The citation check makes sure a cited paper exists; this check asks whether the paper says
what the sentence claims. For every sentence that cites papers, the claim (the sentence
without its citations) is compared with the text Magonia was given from each cited paper:
the passages of its full text, or its title and abstract.

Code finds, for each claim, the closest text from its cited papers, by meaning (embeddings)
or by shared words. Closeness says the passage is about the same thing, not that it agrees:
"olive groves respond to long SPEI timescales in summer" and "only to short timescales in
winter" are equally close to the same passage. So code only rules out claims whose papers
say nothing on the subject, and the language model, asked one strict question about one claim
and one passage, decides the rest:

- supported: the passage says it (the judge answered yes)
- unclear: it partly says it, or there was no judge to ask
- not supported: the cited papers do not say it

What the model was given is a dozen passages chosen for the question, not for the sentences
it then wrote. A paper can say what a sentence claims on a page that was not given, and a
true statement would be withdrawn for it. So a statement the given passages do not support
gets a second look, in the whole text of the papers it cites as kept in the library (`more`):
the passages closest to the claim are judged the same way. A statement supported there is
supported, with its grounding marked "paper" rather than "given", so the reader knows the
model wrote it from memory and the paper happens to bear it out, and the source names the
page that does. Faithfulness is the share of cited statements that are supported.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from engine.citations import GROUP, numbers
from engine.rank import Embed, cosine, words

# Below this, the cited papers are about something else. Measured with nomic-embed-text on
# real passages: unrelated claims 0.58-0.63, claims on the passage's subject 0.69-0.87
OFF_TOPIC = 0.65
# The same, as the share of the claim's content words found in the passage
OFF_TOPIC_WORDS = 0.3

MAX_JUDGED = 20  # each judgement is a call to the model, about a second each
CANDIDATES = 2  # passages asked about per claim, closest first

# A sentence ends at . ! or ? followed by a space, or at a line break
SENTENCE = re.compile(r"[^\n]+?(?:[.!?](?=\s|$)|(?=\n)|$)")
# Dots that do not end a sentence: in citations such as [1, p. 6], and in abbreviations,
# and a genus shortened to its initial, as in "N. vitifusiforme"
NOT_AN_END = re.compile(
    r"\[[^\]]*\]|\bet al\.|\be\.g\.|\bi\.e\.|\bFig\.|\bcf\.|(?-i:\b[A-Z]\.(?= [a-z]))",
    re.IGNORECASE,
)

# A reference rather than a claim: "Smith et al., 2020.", "Smith and Jones (2019)."
AUTHOR_YEAR = re.compile(
    r"^[A-Z][\w'’-]+(?: et al\.?| (?:and|&) [A-Z][\w'’-]+)?,? \(?\d{4}[a-z]?\)?[.,]?$"
)

Judge = Callable[[str, str], str]  # (claim, passage) → "yes", "partly" or "no"


@dataclass
class Statement:
    start: int  # character positions of the sentence in the answer
    end: int
    claim: str
    cites: list[int]
    status: str  # supported, unclear or unsupported
    evidence: str  # the closest text from the cited papers
    source: str  # where that text comes from, e.g. "[1, p. 6]" or "[2] abstract"
    judged: bool = False  # decided by the judge rather than by code
    # for a supported statement: "given" when a passage the model was given says it, "paper"
    # when one found elsewhere in the paper's full text does
    grounding: str = ""

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "claim": self.claim,
            "cites": self.cites,
            "status": self.status,
            "evidence": self.evidence,
            "source": self.source,
            "judged": self.judged,
            "grounding": self.grounding,
        }


def statements(answer: str) -> list[tuple[int, int, str, list[int]]]:
    """The sentences that cite papers: their span, the claim without citations, the papers.

    A sentence without a citation of its own, in a paragraph that began with one, is about the
    same paper ("[1] Smith found… The study also…"), so it carries that citation, until a
    blank line. A heading, a short line without a full stop, passes its citation on to the
    lines under it but is not itself a claim.
    """
    found = []
    # the dots that do not end sentences are hidden while splitting, keeping every position
    masked = NOT_AN_END.sub(lambda m: m.group(0).replace(".", "\x00"), answer)
    carried: list[int] = []
    for match in SENTENCE.finditer(masked):
        sentence = answer[match.start() : match.end()]
        if re.search(r"\n\s*\n\s*$", answer[: match.start()]):
            carried = []  # a blank line starts a new paragraph
        cites = [n for group in GROUP.finditer(sentence) for n in numbers(group.group(1))]
        if cites:
            carried = cites
        else:
            cites = carried
        claim = " ".join(GROUP.sub("", sentence).split()).strip(" -*#:")
        claim = re.sub(r"\*\*", "", claim)
        heading = not claim.endswith((".", "!", "?")) and len(claim.split()) <= 10
        # a paper's authors and year, or its title set in italics, name it and claim nothing
        reference = bool(AUTHOR_YEAR.match(claim)) or GROUP.sub("", sentence).lstrip(
            " -#"
        ).startswith("*")
        if cites and not heading and not reference and len(words(claim)) >= 3:
            start = match.start() + len(sentence) - len(sentence.lstrip())
            found.append((start, match.end(), claim, list(dict.fromkeys(cites))))
    return found


def judge_with(stream: Callable, errors: tuple[type[Exception], ...] = (OSError,)) -> Judge:
    """A judge that asks the language model one strict question and reads its first word;
    errors are those that mean the model could not be asked."""

    def judge(claim: str, passage: str) -> str:
        question = (
            "Does the passage support the claim? Answer with one word: yes, partly or no.\n\n"
            f"Passage: {passage}\n\nClaim: {claim}"
        )
        try:
            said = "".join(
                piece
                for piece in stream([{"role": "user", "content": question}], None)
                if isinstance(piece, str)
            )
        except errors:  # the model could not be asked: the statement stays unclear
            return "partly"
        first = (re.findall(r"[a-z]+", said.lower()) or ["no"])[0]
        return first if first in ("yes", "partly", "no") else "no"

    return judge


More = Callable[[str, list[int]], list[tuple[str, str]]]  # (claim, papers) → (source, text)


def check_support(
    answer: str,
    evidence: dict[int, list[tuple[str, str]]],
    embed: Embed | None = None,
    judge: Judge | None = None,
    more: More | None = None,
) -> list[Statement]:
    """Each cited statement of the answer, with how well its papers support it.

    evidence maps a paper's number to what was given from it, as (source, text) pairs.
    more, when given, finds the passages closest to a claim in the whole text of the papers
    it cites; a statement the given passages do not support is checked against them too.
    """
    found = statements(answer)
    if not found:
        return []
    claims = [claim for _, _, claim, _ in found]
    chunks = [(n, source, text) for n, given in evidence.items() for source, text in given]
    vectors = None
    if embed is not None and chunks:
        try:
            vectors = embed(
                [f"search_query: {c}" for c in claims]
                + [f"search_document: {text}" for _, _, text in chunks]
            )
        except (OSError, KeyError, ValueError):
            vectors = None  # without embeddings, shared words decide
    result, closest = [], []
    low = OFF_TOPIC if vectors is not None else OFF_TOPIC_WORDS
    for i, (start, end, claim, cites) in enumerate(found):
        scored = []
        for j, (n, source, text) in enumerate(chunks):
            if n not in cites:
                continue
            if vectors is not None:
                score = cosine(vectors[i], vectors[len(claims) + j])
            else:
                asked = words(claim)
                score = len(asked & words(text)) / max(len(asked), 1)
            scored.append((score, source, text))
        # the texts on the claim's subject, closest first
        near = [
            (source, text) for score, source, text in sorted(scored, reverse=True) if score >= low
        ]
        best = near[0] if near else (max(scored)[1:] if scored else ("", ""))
        status = "unclear" if near else "unsupported"
        result.append(Statement(start, end, claim, cites, status, best[1], best[0]))
        closest.append(near[:CANDIDATES])
    if judge is not None:
        calls = 0
        for statement, near in zip(result, closest, strict=True):
            if statement.status != "unclear":
                continue
            # the closest passage may not be the one that says it, so a second is asked too
            verdicts = []
            for source, text in near:
                if calls == MAX_JUDGED:
                    break
                calls += 1
                verdicts.append(judge(statement.claim, text))
                if verdicts[-1] == "yes":
                    statement.source, statement.evidence = source, text
                    break
            if verdicts:
                statement.judged = True
                if "yes" in verdicts:
                    statement.status, statement.grounding = "supported", "given"
                elif "partly" not in verdicts:
                    statement.status = "unsupported"
        # a second look, in the whole text of the cited papers, for what was not supported
        if more is not None:
            for statement in result:
                if statement.status == "supported" or calls == MAX_JUDGED:
                    continue
                for source, text in more(statement.claim, statement.cites)[:CANDIDATES]:
                    if calls == MAX_JUDGED:
                        break
                    calls += 1
                    statement.judged = True
                    if judge(statement.claim, text) == "yes":
                        statement.status, statement.grounding = "supported", "paper"
                        statement.source, statement.evidence = source, text
                        break
    return result


BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*$")  # what is left of a line once its sentence is gone


def withdraw(answer: str, found: list[Statement]) -> tuple[str, list[Statement], list[Statement]]:
    """The answer without the statements its papers do not support.

    Returns the new text, the statements kept (their positions moved to the new text) and
    the statements withdrawn. A line left empty, or holding only its bullet, goes with its
    sentence. When something is withdrawn, the answer says so at its end, so the reader
    knows the evidence for it was not found; the withdrawn sentences are listed with the
    passage each was checked against.
    """
    gone = [s for s in found if s.status == "unsupported"]
    if not gone:
        return answer, found, []
    cuts = []
    for s in gone:
        start, end = s.start, s.end
        line_start = answer.rfind("\n", 0, start) + 1
        line_end = answer.find("\n", end)
        line_end = len(answer) if line_end == -1 else line_end
        rest = answer[line_start:start] + answer[end:line_end]
        if BULLET.match(rest):  # the sentence was the whole line: remove the line
            start, end = line_start, min(line_end + 1, len(answer))
        elif answer[end : end + 1] == " ":  # the space before the next sentence
            end += 1
        cuts.append((start, end))
    cuts.sort()
    text, kept, last = [], [], 0
    for start, end in cuts:
        start = max(start, last)
        text.append(answer[last:start])
        last = max(last, end)
    text.append(answer[last:])

    def moved(pos: int) -> int:
        return pos - sum(min(end, pos) - start for start, end in cuts if start < pos)

    for s in found:
        if s.status != "unsupported":
            kept.append(replace(s, start=moved(s.start), end=moved(s.end)))
    new = "".join(text).rstrip()
    n = len(gone)
    new += (
        f"\n\n*{n} {'statement was' if n == 1 else 'statements were'} withdrawn: "
        f"the papers cited did not support {'it' if n == 1 else 'them'}.*"
    )
    return new, kept, gone


def faithfulness(found: list[Statement]) -> float | None:
    """The share of cited statements that are supported; None when nothing was cited."""
    if not found:
        return None
    return round(sum(s.status == "supported" for s in found) / len(found), 2)
