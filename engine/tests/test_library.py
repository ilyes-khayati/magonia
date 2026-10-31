from dataclasses import replace

import pytest

from engine.fulltext import FullTextError, Passage, passages, without_references
from engine.library import Library, for_the_model
from engine.literature import Paper


def paper(id: str, pdf: str | None = "https://example.org/x.pdf") -> Paper:
    return Paper(id, "A study", [], 2020, None, None, "Abstract.", None, 0, [], pdf_url=pdf)


def page(words: int, word: str = "olive") -> str:
    return " ".join([word] * words)


def test_passages_remember_their_page_and_overlap():
    found = passages([page(150, "first"), page(150, "second")], size=100, overlap=20)
    assert [p.page for p in found] == [1, 1, 2, 2]
    assert found[1].text.split()[0] == "first" and found[1].text.split()[-1] == "second"
    assert all(len(p.text.split()) <= 100 for p in found)


def test_the_reference_list_is_left_out():
    texts = [page(100), page(100), "Results here.\nReferences\nSmith J. 2020. Olives."]
    kept = without_references(texts)
    assert kept[-1] == "Results here.\n"
    # a heading called References early in the paper is not the reference list
    assert without_references(["References\n" + page(50), page(50), page(50)])[0].startswith(
        "References"
    )


def test_a_paper_is_read_once_and_failures_are_remembered(tmp_path):
    calls = []

    def reader(url):
        calls.append(url)
        if "broken" in url:
            raise FullTextError("The link gave a web page, not a PDF.")
        return [Passage(3, page(60))]

    shelf = Library(tmp_path / "library.db", reader=reader)
    assert shelf.add(paper("W1")) == "read"
    assert shelf.add(paper("W1")) == "read"
    assert shelf.add(paper("W2", "https://example.org/broken")) == "unreadable"
    assert shelf.add(paper("W2", "https://example.org/broken")) == "unreadable"
    assert shelf.add(paper("W3", None)) == "abstract only"
    assert len(calls) == 2


def test_best_passages_answer_the_question_a_few_per_paper(tmp_path):
    texts = {
        "W1": [
            Passage(n, f"rainfed olive drought ndvi decline {n} " + page(40, "x"))
            for n in range(1, 6)
        ],
        "W2": [Passage(2, "irrigated citrus yields " + page(40, "y"))],
        "W3": [Passage(4, "olive drought response " + page(40, "z"))],
    }
    shelf = Library(tmp_path / "library.db", reader=lambda url: texts[url])
    papers = {n: replace(paper(id), pdf_url=id) for n, id in ((1, "W1"), (2, "W2"), (3, "W3"))}
    assert shelf.add_all(list(papers.values())) == {"W1": "read", "W2": "read", "W3": "read"}

    best = shelf.best("Does drought lower olive NDVI?", papers, keep=5, per_paper=3)
    assert [f.n for f in best].count(1) == 3  # one long paper cannot fill the answer
    assert 3 in [f.n for f in best]
    assert best[-1].n == 2  # what shares no word with the question comes last
    assert for_the_model(best).splitlines()[2].startswith("[1, p. ")


def test_embeddings_are_stored_and_used(tmp_path):
    def embed(texts):  # the question is close to "groves", far from "wheat"
        return [[1.0, 0.0] if "groves" in t or "search_query" in t else [0.0, 1.0] for t in texts]

    texts = [Passage(1, "wheat " + page(40, "w")), Passage(7, "groves " + page(40, "g"))]
    shelf = Library(tmp_path / "library.db", embed=embed, reader=lambda url: texts)
    shelf.add(paper("W1"))
    best = shelf.best("Anything at all", {1: paper("W1")}, keep=1)
    assert best[0].page == 7


@pytest.mark.parametrize("data", [b"<html>", b""])
def test_a_web_page_is_not_a_pdf(monkeypatch, data):
    import io

    from engine import fulltext

    monkeypatch.setattr(fulltext, "urlopen", lambda *a, **k: io.BytesIO(data))
    with pytest.raises(FullTextError):
        fulltext.read("https://example.org/landing")


def test_a_publisher_refusing_downloads_is_told_apart(monkeypatch, tmp_path):
    from urllib.error import HTTPError

    from engine import fulltext

    def refuse(*args, **kwargs):
        raise HTTPError("https://example.org/x.pdf", 403, "Forbidden", {}, None)

    monkeypatch.setattr(fulltext, "urlopen", refuse)
    assert Library(tmp_path / "library.db", reader=fulltext.read).add(paper("W9")) == "blocked"
