"""What Magonia knows of the researcher's own things: the files in their library, and the papers
cited earlier in the conversation.

Two failures of the evaluation led here. Asked for "the key findings of the paper I uploaded",
Magonia asked for its title: a file entered an answer only when its passages were close enough
to the question, and "the paper I uploaded" is close to nothing in it. And asked about "the
first study you cited", it could not tell which: earlier answers reached the model as text whose
[1] and [2] meant nothing any more. Code now decides both, instead of hoping the model infers
them.
"""

import re
from dataclasses import fields
from datetime import datetime

from engine.citations import GROUP
from engine.literature import Paper

# "the paper I uploaded", "my notes", "the PDF", "which files have I added"
OWN = re.compile(
    r"\b(i|we)('ve| have| had)?( just| already)? (uploaded|added|attached|put in|gave you|"
    r"shared)\b"
    r"|\b(my|our) (own )?(papers?|files?|pdfs?|notes|documents?|uploads?|library|reports?)\b"
    r"|\b(the|this|that) (pdf|file|document|upload|report)s?\b"
    r"|\b(uploaded|attached) (papers?|files?|pdfs?|documents?|notes)\b"
    r"|\bin (my|the) library\b",
    re.IGNORECASE,
)
# ... and also what research has found, which still needs a search
LITERATURE = re.compile(
    r"\b(literature|published|other (studies|papers|research|work)|studies (say|find|show)|"
    r"compare (it|this|them|that) (with|to|against)|does (research|the literature))",
    re.IGNORECASE,
)

# "the second file", "my latest upload", "the last PDF I added"
ORDINAL = re.compile(
    r"\b(first|second|third|fourth|fifth|last|latest|newest|oldest|most recent)\s+"
    r"(?:(?:pdf|uploaded|added)\s+)?(file|paper|pdf|document|upload|note)s?\b",
    re.IGNORECASE,
)
PLACES = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "oldest": 0}

MAX_EARLIER = 6  # papers cited earlier that are carried into the next answer, at most


def asks_about_own_files(text: str) -> bool:
    return bool(OWN.search(text))


def wants_literature(text: str) -> bool:
    return bool(LITERATURE.search(text))


def _names(file: dict) -> list[str]:
    stem = re.sub(r"\.pdf$", "", file["filename"], flags=re.IGNORECASE)
    found = {file["title"], file["filename"], stem, stem.replace("_", " ").replace("-", " ")}
    # a name of one short word ("notes") would match too much
    return [n.lower() for n in found if len(n) >= 6 or len(n.split()) >= 2]


def named_files(text: str, files: list[dict]) -> list[dict]:
    """The files the question names, by title or file name."""
    asked = text.lower()
    return [f for f in files if any(name in asked for name in _names(f))]


def files_by_place(text: str, files: list[dict]) -> list[dict]:
    """The files a question points to by their place in the library, oldest first."""
    chosen = []
    for match in ORDINAL.finditer(text):
        word = match.group(1).lower()
        place = PLACES.get(word, len(files) - 1)  # last, latest, newest, most recent
        if 0 <= place < len(files) and files[place] not in chosen:
            chosen.append(files[place])
    return chosen


def files_asked_about(text: str, files: list[dict]) -> list[dict]:
    """The researcher's files a question is about: those it names or points to by place,
    else all of them when it speaks of its own files ("the paper I uploaded"), else none."""
    named = named_files(text, files) or files_by_place(text, files)
    if named:
        return named
    return list(files) if asks_about_own_files(text) else []


def listing(files: list[dict]) -> str:
    """The library as the model reads it, so that it can say what is there."""
    if not files:
        return (
            "The researcher's library (their own PDFs, added on the Library page and shared by "
            "all workspaces) is empty: they have not added any files."
        )
    lines = [
        (
            f"The researcher's library (their own PDFs, added on the Library page and shared "
            f"by all workspaces) holds {len(files)} {'file' if len(files) == 1 else 'files'}:"
        )
    ]
    for f in files:
        added = _date(f.get("added"))
        pages = f"{f['pages']} {'page' if f['pages'] == 1 else 'pages'}"
        lines.append(
            f"- {f['title']} ({f['filename']}, {pages}{', added ' + added if added else ''})"
        )
    return "\n".join(lines)


def _date(stamp: str | None) -> str:
    try:
        return datetime.fromisoformat(stamp).strftime("%-d %B %Y") if stamp else ""
    except ValueError:
        return ""


# Earlier answers


def paper_from(found: dict) -> Paper:
    """A paper back from the dictionary it was sent to the interface as."""
    known = {f.name for f in fields(Paper)}
    return Paper(**{k: v for k, v in found.items() if k in known})


def earlier_papers(conversation: list[dict]) -> list[Paper]:
    """The papers the earlier answers cited, latest answer first, without repeats."""
    chosen: list[Paper] = []
    for message in reversed(conversation):
        if message.get("role") != "assistant":
            continue
        cited = set(message.get("cited") or [])
        for found in message.get("papers") or []:
            if found.get("n") in cited and all(p.id != found.get("id") for p in chosen):
                chosen.append(paper_from(found))
    return chosen[:MAX_EARLIER]


def named_citations(text: str, papers: dict[int, str]) -> str:
    """[1, p. 6] → (Sghaier et al., 2022, p. 6), for the papers numbered in this text."""

    def name(match: re.Match) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        named = [papers[n] for n in numbers if n in papers]
        if not named:
            return match.group(0)
        page = f", p. {match.group(2)}" if match.group(2) else ""
        return f" ({'; '.join(named)}{page})"

    return GROUP.sub(name, text)


def restated(conversation: list[dict]) -> list[dict]:
    """The conversation as the model reads it: each earlier answer's numbered citations become
    the names of its papers, since the numbers start again with every answer."""
    out = []
    for message in conversation:
        content = str(message.get("content", ""))
        if message.get("role") == "assistant" and message.get("papers"):
            names = {p.get("n"): p.get("short") or p.get("title") for p in message["papers"]}
            content = named_citations(content, names)
        out.append({"role": message["role"], "content": content})
    return out
