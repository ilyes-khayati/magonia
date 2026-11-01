"""The researcher's library: every paper Magonia has read, kept as passages, and the search
for the passages that answer a question.

Reading a PDF and embedding its passages takes seconds, so each paper is read once and kept
in a SQLite file: its passages, their pages and their embeddings (the vectors that say what a
passage is about). A paper that could not be read is remembered too, so it is not tried at
every question.

To answer a question, the question is embedded the same way and compared with every passage
of the papers found; the closest ones, at most a few per paper so one long paper cannot fill
the answer, go to the model with their page numbers. Without an embedding model, passages
are compared by the words they share with the question.

The researcher's own PDFs are kept too, beside the database in files/, named by the SHA-256 of
their bytes: the same file added twice is stored once, and a citation can open the page it
cites. A removed file waits 30 days before it is deleted for good, so that it can be restored.
"""

import copy
import hashlib
import os
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

import numpy as np

from engine.fulltext import FullTextError, Passage, pages, passages, read, title_of
from engine.literature import Paper
from engine.rank import Embed, words

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT, url TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL, added TEXT NOT NULL,
    pages INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS passages (
    paper TEXT NOT NULL, n INTEGER NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL,
    embedding BLOB, PRIMARY KEY (paper, n)
);
"""

BATCH = 32  # passages embedded per request
OWN = 4  # passages of the researcher's own files given with a question, at most
# Below this similarity a file is about something else (see support.OFF_TOPIC)
ON_TOPIC = 0.65
ON_TOPIC_WORDS = 0.3


@dataclass
class Found:
    """A passage chosen for the question, from the paper numbered n in the answer."""

    n: int
    page: int
    text: str
    score: float

    def to_dict(self) -> dict:
        return {"n": self.n, "page": self.page, "text": self.text}


KEEP_REMOVED_DAYS = 30


class Library:
    def __init__(
        self,
        path: Path | str,
        embed: Embed | None = None,
        reader: Callable[[str], list[Passage]] = read,
    ):
        self.path = str(path)
        self.files = Path(self.path).parent / "files"  # the researcher's PDFs, by content hash
        self.embed = embed
        self.reader = reader  # replaced in tests
        self.workspace: int | None = None  # whose files Uploads sees; None: every file
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(uploads)")}
            for column in ("sha", "deleted"):  # keeping files and restoring them, added in 1.5
                if column not in columns:
                    db.execute(f"ALTER TABLE uploads ADD COLUMN {column} TEXT")
            if "workspace" not in columns:  # each workspace its own files, added in 1.6
                db.execute("ALTER TABLE uploads ADD COLUMN workspace INTEGER")
        self.purge()

    def scoped(self, workspace: int) -> "Library":
        """The same library, whose files are those of one workspace. Papers found, passages and
        kept PDFs stay shared: they are a cache, and the same paper reads the same anywhere."""
        mine = copy.copy(self)
        mine.workspace = workspace
        return mine

    def purge(self) -> None:
        """Delete for good the files removed more than 30 days ago."""
        with self.connect() as db:
            old = db.execute(
                "SELECT id, sha FROM uploads WHERE deleted < datetime('now', ?)",
                (f"-{KEEP_REMOVED_DAYS} days",),
            ).fetchall()
            for upload_id, _ in old:
                for table, column in (("passages", "paper"), ("papers", "id"), ("uploads", "id")):
                    db.execute(f"DELETE FROM {table} WHERE {column} = ?", (upload_id,))
            for _, sha in old:
                kept = db.execute("SELECT 1 FROM uploads WHERE sha = ?", (sha,)).fetchone()
                if sha and not kept:
                    (self.files / f"{sha}.pdf").unlink(missing_ok=True)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def status(self, paper_id: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT status FROM papers WHERE id = ?", (paper_id,)).fetchone()
        return row[0] if row else None

    def vectors(self, texts: list[str], prefix: str) -> list[np.ndarray] | None:
        if self.embed is None:
            return None
        try:
            found = []
            for i in range(0, len(texts), BATCH):
                found += self.embed([f"{prefix}: {t}" for t in texts[i : i + BATCH]])
        except (URLError, TimeoutError, KeyError, ValueError):
            return None
        return [np.asarray(v, dtype=np.float32) for v in found]

    def add(self, paper: Paper) -> str:
        """Read the paper's PDF into the library, once; says how it went: read, blocked (the
        publisher refuses downloads), unreadable, or abstract only (no open-access PDF)."""
        if known := self.status(paper.id):
            return known
        if not paper.pdf_url:
            return "abstract only"  # not remembered: the paper may become open access
        try:
            found: list[Passage] = self.reader(paper.pdf_url)
        except FullTextError as exc:
            status = "blocked" if "does not allow" in str(exc) else "unreadable"
            with self.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO papers VALUES (?, ?, ?, ?)",
                    (paper.id, status, str(exc), paper.pdf_url),
                )
            return status
        vectors = self.vectors([p.text for p in found], "search_document")
        with self.connect() as db:
            db.execute("DELETE FROM passages WHERE paper = ?", (paper.id,))
            db.executemany(
                "INSERT INTO passages VALUES (?, ?, ?, ?, ?)",
                [
                    (paper.id, i, p.page, p.text, vectors[i].tobytes() if vectors else None)
                    for i, p in enumerate(found)
                ],
            )
            db.execute(
                "INSERT OR REPLACE INTO papers VALUES (?, 'read', ?, ?)",
                (paper.id, f"{len(found)} passages", paper.pdf_url),
            )
        return "read"

    def add_all(self, papers: list[Paper]) -> dict[str, str]:
        """Read several papers at once; downloads wait on the network, not the computer."""
        with ThreadPoolExecutor(max_workers=6) as pool:
            return dict(zip([p.id for p in papers], pool.map(self.add, papers), strict=True))

    def opening(self, paper_id: str) -> tuple[int, str] | None:
        """The first passage of a paper, with its page."""
        with self.connect() as db:
            row = db.execute(
                "SELECT page, text FROM passages WHERE paper = ? ORDER BY n LIMIT 1",
                (paper_id,),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def best(
        self, question: str, papers: dict[int, Paper], keep: int = 12, per_paper: int = 3
    ) -> list[Found]:
        """The passages of the numbered papers that best answer the question, best first."""
        ids = {p.id: n for n, p in papers.items()}
        if not ids:
            return []
        with self.connect() as db:
            rows = db.execute(
                f"SELECT paper, page, text, embedding FROM passages "
                f"WHERE paper IN ({','.join('?' * len(ids))})",
                list(ids),
            ).fetchall()
        if not rows:
            return []
        asked = self.vectors([question], "search_query")
        scored = []
        for paper, page, text, blob in rows:
            if asked is not None and blob is not None:
                v = np.frombuffer(blob, dtype=np.float32)
                score = float(v @ asked[0] / (np.linalg.norm(v) * np.linalg.norm(asked[0]) or 1))
            else:
                question_words = words(question)
                score = len(question_words & words(text)) / max(len(question_words), 1)
            scored.append(Found(ids[paper], page, text, score))
        scored.sort(key=lambda f: f.score, reverse=True)
        chosen, count = [], {}
        for found in scored:
            if count.get(found.n, 0) < per_paper:
                chosen.append(found)
                count[found.n] = count.get(found.n, 0) + 1
            if len(chosen) == keep:
                break
        return chosen


class Uploads:
    """The researcher's own PDFs, read into the same library as the papers found."""

    def __init__(self, library: Library):
        self.library = library

    def add(self, filename: str, pdf: bytes, title: str | None = None) -> dict:
        """Read an uploaded PDF; raises FullTextError when it has no text to read."""
        texts = pages(pdf)
        found = passages(texts)
        if not found:
            raise FullTextError("The PDF has no text; it may be a scan.")
        lib = self.library
        with lib.connect() as db:
            number = db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0] + 1
            while db.execute("SELECT 1 FROM uploads WHERE id = ?", (f"U{number}",)).fetchone():
                number += 1
        upload_id = f"U{number}"
        vectors = lib.vectors([p.text for p in found], "search_document")
        name = title or title_of(pdf) or Path(filename).stem.replace("_", " ")
        sha = hashlib.sha256(pdf).hexdigest()
        lib.files.mkdir(parents=True, exist_ok=True)
        kept = lib.files / f"{sha}.pdf"
        if not kept.exists():
            kept.write_bytes(pdf)
        with lib.connect() as db:
            db.executemany(
                "INSERT INTO passages VALUES (?, ?, ?, ?, ?)",
                [
                    (upload_id, i, p.page, p.text, vectors[i].tobytes() if vectors else None)
                    for i, p in enumerate(found)
                ],
            )
            db.execute("INSERT INTO papers VALUES (?, 'read', ?, NULL)", (upload_id, "uploaded"))
            db.execute(
                "INSERT INTO uploads (id, title, filename, added, pages, sha, workspace) "
                "VALUES (?, ?, ?, datetime('now'), ?, ?, ?)",
                (upload_id, name, filename, len(texts), sha, lib.workspace),
            )
        return {**self.get(upload_id), "passages": len(found)}

    def get(self, upload_id: str, removed: bool = False) -> dict:
        """A file of the library, with whether its PDF is kept; a removed one only if asked."""
        with self.library.connect() as db:
            row = db.execute(
                "SELECT id, title, filename, added, pages, sha FROM uploads "
                "WHERE id = ? AND (deleted IS NULL OR ?)",
                (upload_id, removed),
            ).fetchone()
        if row is None:
            raise KeyError(upload_id)
        found = dict(zip(("id", "title", "filename", "added", "pages"), row[:5], strict=True))
        return {**found, "pdf": bool(row[5]) and (self.library.files / f"{row[5]}.pdf").exists()}

    def all(self) -> list[dict]:
        """The files of the library's workspace, or every file when it has none."""
        workspace = self.library.workspace
        with self.library.connect() as db:
            if workspace is not None:
                # files added before they belonged to a workspace go to the first one opened
                db.execute("UPDATE uploads SET workspace = ? WHERE workspace IS NULL", (workspace,))
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM uploads WHERE deleted IS NULL AND (? IS NULL OR workspace = ?) "
                    "ORDER BY added, id",
                    (workspace, workspace),
                )
            ]
        return [self.get(i) for i in ids]

    def remove(self, upload_id: str) -> None:
        """Remove a file from the library; it can be restored for 30 days."""
        self.get(upload_id)
        with self.library.connect() as db:
            db.execute("UPDATE uploads SET deleted = datetime('now') WHERE id = ?", (upload_id,))

    def restore(self, upload_id: str) -> dict:
        self.get(upload_id, removed=True)
        with self.library.connect() as db:
            db.execute("UPDATE uploads SET deleted = NULL WHERE id = ?", (upload_id,))
        return self.get(upload_id)

    def pdf(self, upload_id: str) -> Path | None:
        """The kept PDF of a file, if there is one (files added before 1.5 were not kept)."""
        with self.library.connect() as db:
            row = db.execute(
                "SELECT sha FROM uploads WHERE id = ? AND deleted IS NULL", (upload_id,)
            ).fetchone()
        if row is None:
            raise KeyError(upload_id)
        path = self.library.files / f"{row[0]}.pdf" if row[0] else None
        return path if path and path.exists() else None

    def papers(self) -> list[Paper]:
        """Each file as a paper, named by its title, to be cited like the papers found."""
        return [
            Paper(
                u["id"],
                u["title"],
                [],
                None,
                "Your library",
                None,
                None,
                None,
                0,
                [],
                label=u["title"],
            )
            for u in self.all()
        ]

    def asked_about(
        self, question: str, files: list[dict], first: int, keep: int = 2
    ) -> tuple[list[Paper], list[Found]]:
        """Files the question is about, numbered from first, with their passages that answer it
        best and their opening passage, which usually says what the file is. No similarity
        threshold: the researcher asked for these files. Of many, the closest few are kept."""
        wanted = {f["id"] for f in files}
        mine = [p for p in self.papers() if p.id in wanted]
        if not mine:
            return [], []
        numbered = {first + i: p for i, p in enumerate(mine)}
        found = self.library.best(question, numbered, keep=OWN * len(mine), per_paper=OWN)
        kept = list(dict.fromkeys(f.n for f in found))[:keep] or list(numbered)[:keep]
        chosen = [f for f in found if f.n in kept][: OWN + 1]
        for n in kept:  # the opening passage, unless it was chosen already
            opening = self.library.opening(numbered[n].id)
            if opening and not any(f.n == n and f.text == opening[1] for f in chosen):
                chosen.insert(0, Found(n, opening[0], opening[1], 1.0))
        renumber = {old: first + i for i, old in enumerate(kept)}
        for f in chosen:
            f.n = renumber[f.n]
        return [numbered[old] for old in kept], chosen

    def relevant(self, question: str, first: int) -> tuple[list[Paper], list[Found]]:
        """The files that speak to the question, numbered from first, and their passages."""
        mine = self.papers()
        if not mine:
            return [], []
        numbered = {first + i: p for i, p in enumerate(mine)}
        found = self.library.best(question, numbered, keep=OWN, per_paper=2)
        low = ON_TOPIC if self.library.embed is not None else ON_TOPIC_WORDS
        found = [f for f in found if f.score >= low]
        # renumber the files that were kept from first, in the order they are first used
        kept = list(dict.fromkeys(f.n for f in found))
        renumber = {old: first + i for i, old in enumerate(kept)}
        for f in found:
            f.n = renumber[f.n]
        return [numbered[old] for old in kept], found


def for_the_model(found: list[Found]) -> str:
    """The chosen passages as the model reads them, grouped by paper, with their pages."""
    if not found:
        return ""
    lines = [
        (
            "Passages from the full text of these papers. Prefer them to the abstracts, and "
            "cite the page with the paper, e.g. [1, p. 6]."
        )
    ]
    for f in sorted(found, key=lambda f: (f.n, f.page)):
        lines.append(f"[{f.n}, p. {f.page}] {f.text}")
    return "\n\n".join(lines)


def default_path() -> Path:
    """library.db beside Magonia's database: ~/.magonia, or the folder in MAGONIA_DATA_DIR."""
    folder = Path(os.environ.get("MAGONIA_DATA_DIR", Path.home() / ".magonia"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "library.db"
