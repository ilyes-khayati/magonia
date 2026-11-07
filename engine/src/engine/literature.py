"""Searching the scholarly literature through OpenAlex (about 250 million works, free API)."""

import json
import logging
import os
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


def search_papers(query: str, limit: int = 6, from_year: int | None = None) -> list[Paper]:
    """The works that best match the query, by OpenAlex relevance."""
    load_dotenv()
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
    except HTTPError as exc:
        if exc.code == 429:
            if not key:  # for whoever runs Magonia, not for the researcher
                log.warning("OpenAlex budget used up: a free key in OPENALEX_API_KEY gives its own")
            raise LiteratureError(
                "The literature search has reached its daily limit; it starts again at "
                "midnight UTC. Answers from your data and your files still work."
            ) from exc
        raise LiteratureError("The literature search failed. Try again in a minute.") from exc
    except (URLError, TimeoutError) as exc:
        raise LiteratureError(
            "The literature search cannot be reached right now. Try again in a minute."
        ) from exc
    return [to_paper(work) for work in found.get("results", [])]


# How many works to fetch before ranking; more finds better papers but takes longer
CANDIDATES = 30


def find_papers(query: str, question: str, keep: int = 6, embed=None) -> list[Paper]:
    """Many candidates for the query, ranked against the researcher's question."""
    from engine.rank import rank

    return rank(question or query, search_papers(query, limit=CANDIDATES), keep, embed)
