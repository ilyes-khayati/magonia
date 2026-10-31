from urllib.error import URLError

from engine.literature import Paper
from engine.rank import rank, words


def paper(title: str, abstract: str | None = "", cited_by: int = 0) -> Paper:
    return Paper(title, title, [], 2020, None, None, abstract, None, cited_by, [])


QUESTION = "Does drought reduce olive NDVI in the same season?"


def test_common_words_are_not_content():
    assert words(QUESTION) == {"drought", "reduce", "olive", "ndvi", "season"}


def test_shared_words_rank_and_explain_without_embeddings():
    papers = [
        paper("Wheat yields in Canada", "Wheat and barley."),
        paper("Drought and olive NDVI", "Olive groves lose NDVI in a dry season."),
    ]
    ranked = rank(QUESTION, papers, keep=2)
    assert ranked[0].title == "Drought and olive NDVI"
    assert ranked[0].matched == ["drought", "ndvi", "olive", "season"]
    assert ranked[0].relevance > ranked[1].relevance


def test_meaning_outranks_words_when_embeddings_exist():
    papers = [paper("Olive drought", "olive drought"), paper("Water stress in groves", "dry")]

    def embed(texts):  # the question is closest to the second paper
        return [[1.0, 0.0], [0.0, 1.0], [1.0, 0.1]]

    assert rank(QUESTION, papers, keep=1, embed=embed)[0].title == "Water stress in groves"


def test_a_missing_embedding_model_falls_back_to_words():
    def embed(texts):
        raise URLError("model not found")

    papers = [paper("Rice", "rice"), paper("Olive drought", "olive drought")]
    assert rank(QUESTION, papers, keep=1, embed=embed)[0].title == "Olive drought"


def test_citations_break_ties_and_missing_abstracts_go_last():
    papers = [
        paper("Olive drought", None, cited_by=500),
        paper("Olive drought NDVI", "x", cited_by=1),
        paper("Drought NDVI olive", "x", cited_by=90),
    ]
    ranked = rank(QUESTION, papers, keep=3)
    assert [p.cited_by for p in ranked] == [90, 500]  # the duplicate title is kept once


def test_keep_limits_the_list():
    assert len(rank(QUESTION, [paper(f"Olive site{n}") for n in range(6)], keep=4)) == 4
    assert rank(QUESTION, [], keep=4) == []
