"""Searching the scholarly literature through OpenAlex (about 250 million works, free API)."""

import json
import os
import ssl
from dataclasses import asdict, dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv

OPENALEX = "https://api.openalex.org/works"
FIELDS = (
    "id,doi,title,publication_year,authorships,primary_location,"
    "abstract_inverted_index,open_access,cited_by_count"
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

    @property
    def short(self) -> str:
        """Author–year form, e.g. "Sghaier et al., 2022"."""
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
    )


def search_papers(query: str, limit: int = 6, from_year: int | None = None) -> list[Paper]:
    """The works that best match the query, by OpenAlex relevance."""
    load_dotenv()
    params = {"search": query, "per_page": limit, "select": FIELDS}
    if from_year:
        params["filter"] = f"publication_year:>{from_year - 1}"
    # Optional: OpenAlex answers faster and more reliably when given a contact address
    if email := os.environ.get("OPENALEX_EMAIL"):
        params["mailto"] = email
    request = Request(f"{OPENALEX}?{urlencode(params)}", headers={"User-Agent": "Magonia"})
    try:
        with urlopen(request, timeout=30, context=CERTIFICATES) as response:
            found = json.load(response)
    except (URLError, TimeoutError) as exc:
        raise LiteratureError(f"Could not reach OpenAlex: {exc}") from exc
    return [to_paper(work) for work in found.get("results", [])]
