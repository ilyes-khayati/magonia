import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from engine import literature
from engine.literature import LiteratureError, abstract, search_papers

# A real OpenAlex answer for "drought olive NDVI Mediterranean", recorded and trimmed
RECORDED = Path(__file__).parent / "data" / "openalex_drought_olive.json"


@pytest.fixture
def openalex(monkeypatch):
    asked = []

    def fake_urlopen(request, timeout, context=None):
        asked.append(request.full_url)
        return io.BytesIO(RECORDED.read_bytes())

    monkeypatch.setattr(literature, "urlopen", fake_urlopen)
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)
    monkeypatch.setattr(literature, "load_dotenv", lambda: None)
    return asked


def test_abstract_is_rebuilt_in_word_order():
    assert abstract({"olive": [1], "Rainfed": [0], "groves.": [2]}) == "Rainfed olive groves."
    assert abstract(None) is None


def test_recorded_search_becomes_clean_papers(openalex):
    papers = search_papers("drought olive NDVI Mediterranean", limit=5)

    assert len(papers) == 5
    first = papers[0]
    assert first.title == "Assessment of drought stress in arid olive groves using HidroMORE model"
    assert first.short == "Sghaier et al., 2022"
    assert first.doi == "10.4081/jae.2022.1264"
    assert first.venue == "Journal of Agricultural Engineering"
    assert first.abstract and first.abstract.startswith(first.abstract.split()[0])
    assert "TN" in first.countries
    assert "search=drought+olive+NDVI+Mediterranean" in openalex[0]


def test_year_filter_and_contact_email_are_sent(openalex, monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "someone@example.org")
    search_papers("olive", from_year=2020)
    assert "publication_year%3A%3E2019" in openalex[0]
    assert "mailto=someone%40example.org" in openalex[0]


def test_short_names_follow_author_count():
    work = json.loads(RECORDED.read_text())["results"][0]
    one = literature.to_paper({**work, "authorships": work["authorships"][:1]})
    two = literature.to_paper({**work, "authorships": work["authorships"][:2]})
    assert one.short == "Sghaier, 2022"
    assert two.short.startswith("Sghaier and ")


def test_an_api_key_is_sent_when_set(openalex, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "k123")
    search_papers("olive")
    assert "api_key=k123" in openalex[0]


def test_a_used_up_budget_says_so_and_logs_how_to_fix_it(monkeypatch, caplog):
    def limited(request, timeout, context=None):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(literature, "load_dotenv", lambda: None)
    monkeypatch.setattr(literature, "urlopen", limited)
    with pytest.raises(LiteratureError, match="daily limit"):
        search_papers("olive")
    assert "OPENALEX_API_KEY" in caplog.text


def test_unreachable_openalex_is_a_clear_error(monkeypatch):
    def offline(request, timeout, context=None):
        raise URLError("no network")

    monkeypatch.setattr(literature, "urlopen", offline)
    with pytest.raises(LiteratureError, match="cannot be reached right now"):
        search_papers("olive")


def test_a_second_search_uses_the_questions_own_words(monkeypatch):
    from engine.literature import Paper, find_papers, keywords

    assert (
        keywords("What do studies say about drought and olive NDVI in Spain?")
        == "drought olive NDVI Spain"
    )
    asked = []

    def fake(query, limit=30, **kwargs):
        asked.append(query)
        return [
            Paper(f"W{len(asked)}{i}", f"{query} {i}", ["A"], 2020, None, None, query, None, 0, [])
            for i in range(3)
        ]

    monkeypatch.setattr(literature, "search_papers", fake)
    found = find_papers(
        "olive drought remote sensing", "What do studies say about drought and olive NDVI in Spain?"
    )
    assert asked == ["olive drought remote sensing", "drought olive NDVI Spain"]
    # the second search's papers, about the question itself, rank first
    assert found and found[0].title.startswith("drought olive NDVI Spain")


def test_an_opening_that_only_announces_the_answer_is_dropped():
    from engine.citations import check

    paper = literature.Paper("W1", "Olive drought", ["A"], 2020, None, None, None, None, 0, [])
    found = check(
        "Based on the literature, here is what is known:\n\nOlive NDVI falls in drought [1].",
        [paper],
    )
    assert found.text == "Olive NDVI falls in drought [1]."
