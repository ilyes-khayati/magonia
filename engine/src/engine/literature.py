"""Searching the scholarly literature through OpenAlex (about 250 million works, free API)."""

import json
import logging
import os
import re
import ssl
from dataclasses import asdict, dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv

log = logging.getLogger("magonia")

OPENALEX = "https://api.openalex.org/works"
FIELDS = (
    "id,doi,title,publication_year,authorships,primary_location,"
    "abstract_inverted_index,open_access,best_oa_location,cited_by_count"
)


# Python on macOS does not always trust the system certificates, so bring a known bundle
CERTIFICATES = ssl.create_default_context(cafile=certifi.where())


class LiteratureError(Exception):
    """The literature service could not be reached or answered with an error."""


@dataclass
class Paper:
    id: str  # OpenAlex work id, e.g. W4220927011
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    abstract: str | None
    open_access_url: str | None
    cited_by: int
    countries: list[str]  # where the authors' institutions are
    pdf_url: str | None = None  # the open-access PDF itself, when there is one
    label: str | None = None  # how to name it instead of authors and year, e.g. a file name
    relevance: float | None = None  # how well it answers the question, set when ranked
    matched: list[str] = field(default_factory=list)  # words it shares with the question

    @property
    def short(self) -> str:
        """Author–year form, e.g. "Sghaier et al., 2022"."""
        if self.label:
            return self.label
        surnames = [name.split()[-1] for name in self.authors]
        if not surnames:
            names = "Anonymous"
        elif len(surnames) == 1:
            names = surnames[0]
        elif len(surnames) == 2:
            names = f"{surnames[0]} and {surnames[1]}"
        else:
            names = f"{surnames[0]} et al."
        return f"{names}, {self.year or 'n.d.'}"

    def to_dict(self) -> dict:
        return {**asdict(self), "short": self.short}


def abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as word → positions; put the words back in order."""
    if not inverted:
        return None
    words = sorted(
        (position, word) for word, positions in inverted.items() for position in positions
    )
    return " ".join(word for _, word in words)


def to_paper(work: dict) -> Paper:
    source = (work.get("primary_location") or {}).get("source") or {}
    doi = work.get("doi")
    return Paper(
        id=work["id"].rsplit("/", 1)[-1],
        title=work.get("title") or "(untitled)",
        authors=[a["author"]["display_name"] for a in work.get("authorships", [])],
        year=work.get("publication_year"),
        venue=source.get("display_name"),
        doi=doi.removeprefix("https://doi.org/") if doi else None,
        abstract=abstract(work.get("abstract_inverted_index")),
        open_access_url=(work.get("open_access") or {}).get("oa_url"),
        cited_by=work.get("cited_by_count") or 0,
        countries=sorted({c for a in work.get("authorships", []) for c in a.get("countries", [])}),
        pdf_url=(work.get("best_oa_location") or {}).get("pdf_url"),
    )


def search_papers(
    query: str,
    limit: int = 6,
    from_year: int | None = None,
    semantic: bool = False,
    fallback: bool = True,
) -> list[Paper]:
    """The works that best match the query, by OpenAlex relevance: on the words of their title
    and abstract, or, semantic, on meaning (OpenAlex embeds titles, abstracts and venues;
    at most 50 results and one request a second)."""
    load_dotenv()
    if semantic:
        params = {"search.semantic": query[:2000], "per_page": min(limit, 50), "select": FIELDS}
    else:
        params = {"search": query, "per_page": limit, "select": FIELDS}
    if from_year:
        params["filter"] = f"publication_year:>{from_year - 1}"
    # Without a key, OpenAlex gives a small free budget a day, shared by everyone on the same
    # network address; a free key gives this installation its own
    if key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = key
    # Optional: OpenAlex answers faster and more reliably when given a contact address
    if email := os.environ.get("OPENALEX_EMAIL"):
        params["mailto"] = email
    request = Request(f"{OPENALEX}?{urlencode(params)}", headers={"User-Agent": "Magonia"})
    try:
        with urlopen(request, timeout=30, context=CERTIFICATES) as response:
            found = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        # OpenAlex down or out of budget: Crossref, a second index, keeps the search working
        # (by words only: Crossref has no search by meaning)
        if fallback and not semantic and (backup := search_crossref(query, limit, from_year)):
            log.warning("OpenAlex unavailable (%s); searched Crossref instead", exc)
            return backup
        return _openalex_failed(exc, key)
    return [to_paper(work) for work in found.get("results", [])]


def _openalex_failed(exc: Exception, key: str | None) -> list[Paper]:
    """The researcher's message for an OpenAlex failure that no backup could cover."""
    if isinstance(exc, HTTPError) and exc.code == 429:
        if not key:  # for whoever runs Magonia, not for the researcher
            log.warning("OpenAlex budget used up: a free key in OPENALEX_API_KEY gives its own")
        raise LiteratureError(
            "The literature search has reached its daily limit; it starts again at "
            "midnight UTC. Answers from your data and your files still work."
        ) from exc
    if isinstance(exc, HTTPError):
        raise LiteratureError("The literature search failed. Try again in a minute.") from exc
    raise LiteratureError(
        "The literature search cannot be reached right now. Try again in a minute."
    ) from exc


CROSSREF = "https://api.crossref.org/works"


def crossref_paper(item: dict) -> Paper:
    """A Crossref record as a Paper. Crossref abstracts, when present, are JATS XML."""
    doi = item.get("DOI")
    text = re.sub(r"<[^>]+>", " ", item.get("abstract") or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^Abstract\s+", "", text)
    year = ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    authors = [
        " ".join(x for x in (a.get("given"), a.get("family")) if x) for a in item.get("author", [])
    ]
    return Paper(
        id=f"doi:{doi.lower()}" if doi else f"crossref:{item.get('URL', '')}",
        title=(item.get("title") or ["(untitled)"])[0],
        authors=[a for a in authors if a],
        year=year,
        venue=(item.get("container-title") or [None])[0],
        doi=doi.lower() if doi else None,
        abstract=text or None,
        open_access_url=None,
        cited_by=item.get("is-referenced-by-count") or 0,
        countries=[],
    )


def search_crossref(query: str, limit: int = 6, from_year: int | None = None) -> list[Paper]:
    """The works Crossref ranks first for the query, journal articles only. Used when OpenAlex
    cannot be reached; returns [] when Crossref cannot either."""
    params = {"query.bibliographic": query, "rows": limit, "filter": "type:journal-article"}
    if from_year:
        params["filter"] += f",from-pub-date:{from_year}"
    request = Request(f"{CROSSREF}?{urlencode(params)}", headers={"User-Agent": "Magonia"})
    try:
        with urlopen(request, timeout=30, context=CERTIFICATES) as response:
            items = json.load(response).get("message", {}).get("items", [])
    except (HTTPError, URLError, TimeoutError, ValueError):
        return []
    return [crossref_paper(item) for item in items if item.get("title")]


# How many works to fetch before ranking; more finds better papers but takes longer
CANDIDATES = 30
# and, searching by meaning too, how many more
SEMANTIC_CANDIDATES = 20


# Words a search engine matches on but that say nothing about the topic
STOPWORD_TEXT = """a an and are as at be by can could did do does done for from has have how
i in into is it its my of on or our over so studies study say says than that the their them
then there these they this to was we were what when where which while who why will with would
about any known research papers paper literature found find show shown"""
STOPWORDS = frozenset(STOPWORD_TEXT.split())


def keywords(question: str, most: int = 8) -> str:
    """The question's topic words, as a search query: for a follow-up searched by code."""
    words = re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9-]*", question)
    kept = [w for w in words if w.lower() not in STOPWORDS and len(w) > 2]
    return " ".join(list(dict.fromkeys(kept))[:most])


def find_papers(
    query: str, question: str, keep: int = 6, embed=None, hybrid: bool = False
) -> list[Paper]:
    """Candidates for the model's query, ranked against the question. A second search on the
    question's own words was measured and dropped: it found no more relevant papers, brought
    off-topic ones to trap questions, and used the daily search budget twice as fast.

    Hybrid adds a search by meaning on the question itself, which finds papers that say the
    same thing in other words; keywords still catch exact terms (SPEI-6, a site's name). The
    two lists are merged before ranking. It is off by default until measured: a search by
    meaning always returns something, so it must be shown not to bring papers to trap
    questions."""
    from engine.rank import rank

    candidates = search_papers(query, limit=CANDIDATES)
    if hybrid:
        try:
            more = search_papers(question or query, limit=SEMANTIC_CANDIDATES, semantic=True)
        except LiteratureError:  # the keyword results still stand
            more = []
        seen = {p.id for p in candidates}
        candidates += [p for p in more if p.id not in seen]
    return rank(question or query, candidates, keep, embed)
