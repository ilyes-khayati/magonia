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
"""

import os
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

import numpy as np

from engine.fulltext import FullTextError, Passage, read
from engine.literature import Paper
from engine.rank import Embed, words

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT, url TEXT
);
CREATE TABLE IF NOT EXISTS passages (
    paper TEXT NOT NULL, n INTEGER NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL,
    embedding BLOB, PRIMARY KEY (paper, n)
);
"""

BATCH = 32  # passages embedded per request


@dataclass
class Found:
    """A passage chosen for the question, from the paper numbered n in the answer."""

    n: int
    page: int
    text: str
    score: float

    def to_dict(self) -> dict:
        return {"n": self.n, "page": self.page, "text": self.text}


class Library:
    def __init__(
        self,
        path: Path | str,
        embed: Embed | None = None,
        reader: Callable[[str], list[Passage]] = read,
    ):
        self.path = str(path)
        self.embed = embed
        self.reader = reader  # replaced in tests
        with self.connect() as db:
            db.executescript(SCHEMA)

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
