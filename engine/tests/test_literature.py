import io
import json
from pathlib import Path
from urllib.error import URLError

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


def test_unreachable_openalex_is_a_clear_error(monkeypatch):
    def offline(request, timeout, context=None):
        raise URLError("no network")

    monkeypatch.setattr(literature, "urlopen", offline)
    with pytest.raises(LiteratureError, match="Could not reach OpenAlex"):
        search_papers("olive")
