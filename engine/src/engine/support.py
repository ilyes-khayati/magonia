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

- supported: the passage says it (the model answered yes)
- unclear: it partly says it, or there was no model to ask
- not supported: the cited papers do not say it

Faithfulness is the share of cited statements that are supported.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

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
# Dots that do not end a sentence: in citations such as [1, p. 6], and in abbreviations
NOT_AN_END = re.compile(r"\[[^\]]*\]|\bet al\.|\be\.g\.|\bi\.e\.|\bFig\.|\bcf\.", re.IGNORECASE)

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
    judged: bool = False  # decided by the language model rather than by code

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
        if cites and not heading and len(words(claim)) >= 3:
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


def check_support(
    answer: str,
    evidence: dict[int, list[tuple[str, str]]],
    embed: Embed | None = None,
    judge: Judge | None = None,
) -> list[Statement]:
    """Each cited statement of the answer, with how well its papers support it.

    evidence maps a paper's number to what was given from it, as (source, text) pairs.
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
                    statement.status = "supported"
                elif "partly" not in verdicts:
                    statement.status = "unsupported"
    return result


def faithfulness(found: list[Statement]) -> float | None:
    """The share of cited statements that are supported; None when nothing was cited."""
    if not found:
        return None
    return round(sum(s.status == "supported" for s in found) / len(found), 2)
