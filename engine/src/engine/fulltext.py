"""Reading a paper's full text: its open-access PDF, page by page, cut into passages.

An abstract says what a paper claims; the evidence, the site and the caveats are in the body.
So for each open-access paper Magonia downloads the PDF, takes out the text of each page and
cuts it into passages of about 200 words, each remembering its page, so an answer can say
where in the paper a statement comes from. The reference list is left out: it names other
papers, it does not say what this one found.

Only open-access PDFs are read; a paper behind a paywall stays at its abstract.
"""

import io
import logging
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from engine.literature import CERTIFICATES

PASSAGE_WORDS = 200  # about a paragraph: long enough to hold a finding with its context
OVERLAP = 40  # words shared by neighbouring passages, so a sentence cut in two is in one whole
MAX_PAGES = 40  # beyond this it is a thesis or a book, and the start says what matters
MAX_BYTES = 30_000_000

# Some publishers refuse requests that do not look like a browser
HEADERS = {"User-Agent": "Mozilla/5.0 (Magonia research assistant)", "Accept": "application/pdf"}

REFERENCES = re.compile(
    r"^\s*(references|bibliography|literature cited)\s*$", re.IGNORECASE | re.MULTILINE
)


# pypdf warns about every font it cannot fully decode; the text comes out regardless
logging.getLogger("pypdf").setLevel(logging.ERROR)


class FullTextError(Exception):
    """The PDF could not be downloaded or read."""


@dataclass
class Passage:
    page: int  # 1-based, as printed in a PDF viewer
    text: str


def download(url: str, timeout: float = 15) -> bytes:
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=timeout, context=CERTIFICATES) as response:
            data = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise FullTextError("The publisher does not allow downloads.") from exc
        raise FullTextError(f"Could not download the PDF: {exc}") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise FullTextError(f"Could not download the PDF: {exc}") from exc
    if not data.startswith(b"%PDF"):
        raise FullTextError("The link gave a web page, not a PDF.")
    if len(data) > MAX_BYTES:
        raise FullTextError("The PDF is too large.")
    return data


def pages(pdf: bytes) -> list[str]:
    """The text of each page, with words broken across lines joined again."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        texts = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise FullTextError(f"Could not read the PDF: {exc}") from exc
    return [re.sub(r"(\w)-\n(\w)", r"\1\2", t) for t in texts]


def title_of(pdf: bytes) -> str | None:
    """The title a PDF carries in its metadata, when it looks like one: publishers set it,
    while word processors leave a file name or "Microsoft Word - draft.docx"."""
    try:
        title = (PdfReader(io.BytesIO(pdf)).metadata or {}).get("/Title")
    except (PdfReadError, ValueError, KeyError, TypeError):
        return None
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if len(title.split()) < 3 or len(title) > 300:
        return None
    if re.search(r"^(microsoft|untitled)|\.(docx?|pdf|tex|odt)$", title, re.IGNORECASE):
        return None
    return title


def without_references(texts: list[str]) -> list[str]:
    """The pages up to the reference list, when it starts in the second half of the paper."""
    for i in range(len(texts) - 1, len(texts) // 2 - 1, -1):
        if match := REFERENCES.search(texts[i]):
            return texts[:i] + [texts[i][: match.start()]]
    return texts


def passages(texts: list[str], size: int = PASSAGE_WORDS, overlap: int = OVERLAP) -> list[Passage]:
    """Passages of about size words, each with the page where it starts."""
    words = [(n, w) for n, text in enumerate(without_references(texts), 1) for w in text.split()]
    found = []
    step = size - overlap
    for start in range(0, max(len(words) - overlap, 1), step):
        chunk = words[start : start + size]
        if len(chunk) >= 30:  # a few words at the end of a page say nothing on their own
            found.append(Passage(chunk[0][0], " ".join(w for _, w in chunk)))
    return found


def read(url: str) -> list[Passage]:
    """The passages of the PDF at url."""
    found = passages(pages(download(url)))
    if not found:
        raise FullTextError("The PDF has no text; it may be a scan.")
    return found
