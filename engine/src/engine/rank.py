"""Choosing the few papers worth reading from many candidates, for the researcher's question.

OpenAlex orders works by how well they match the search words, which the model chose. The
researcher's own question says more, so many candidates are fetched and ranked against it:

- by meaning, when an embedding model is available: question and paper are each turned into
  a vector of numbers (an embedding) and compared by cosine similarity, so "water stress"
  can match "drought" without sharing a word
- by shared words otherwise: the share of the question's content words that the title and
  abstract contain

A small bonus goes to papers that are cited more, and papers without an abstract go last,
because there is nothing to read in them. A work listed twice is kept once. Each ranked paper keeps the words it shares with
the question, so the researcher can see why it was chosen.
"""

import json
import math
import re
from collections.abc import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from engine.literature import Paper

Embed = Callable[[list[str]], list[list[float]]]

# How much citations count against relevance; relevance always dominates
CITATION_WEIGHT = 0.1
# Papers less similar to the question than this are not given to the model: in the evaluation
# no paper judged relevant scored below it, and a third of those judged irrelevant did
FLOOR = 0.6

COMMON = """a an and are as at be by can do does did for from has have how i in is it its of on or
    our my that the their them these this those to was were what when where which who why
    will with within about after before between during into over under than then there
    studies study papers paper research published literature found find show shows known say
    says tell me us you your same also more most other"""
STOPWORDS = set(COMMON.split())


def words(text: str) -> set[str]:
    """The content words of a text, lower case, without the common ones."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1}


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def ollama_embedder(url: str, model: str = "nomic-embed-text") -> Embed:
    """Embeddings from an Ollama server; raises URLError when the model is not there."""

    def embed(texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": model, "input": texts}).encode()
        request = Request(f"{url}/api/embed", body, {"Content-Type": "application/json"})
        with urlopen(request, timeout=60) as response:
            return json.load(response)["embeddings"]

    return embed


def rank(question: str, papers: list[Paper], keep: int, embed: Embed | None = None) -> list[Paper]:
    """The keep papers most relevant to the question, best first, with their relevance set."""
    if not papers:
        return []
    asked = words(question)
    texts = [f"{p.title}. {p.abstract or ''}" for p in papers]
    similarity = None
    if embed is not None:
        try:
            # nomic-embed-text expects these prefixes for questions and documents
            vectors = embed(
                [f"search_query: {question}"] + [f"search_document: {t}" for t in texts]
            )
            similarity = [cosine(vectors[0], v) for v in vectors[1:]]
        except (URLError, TimeoutError, KeyError, ValueError):
            similarity = None  # no embedding model: fall back to shared words
    most_cited = max(p.cited_by for p in papers)
    for i, (paper, text) in enumerate(zip(papers, texts, strict=True)):
        shared = asked & words(text)
        paper.matched = sorted(shared)
        if similarity is not None:
            relevance = similarity[i]
        else:
            relevance = len(shared) / len(asked) if asked else 0.0
        cited = math.log1p(paper.cited_by) / math.log1p(most_cited) if most_cited else 0.0
        paper.relevance = round(relevance + CITATION_WEIGHT * cited, 3)
    ranked = sorted(papers, key=lambda p: (p.abstract is not None, p.relevance), reverse=True)
    # the same work is often listed twice, as a preprint and as the published version
    seen, unique = set(), []
    for paper in ranked:
        title = " ".join(sorted(words(paper.title)))
        if title not in seen:
            seen.add(title)
            unique.append(paper)
    if similarity is not None:
        # an off-topic paper is worse than none: the model then says nothing was found
        unique = [p for p in unique if p.relevance >= FLOOR]
    return unique[:keep]
