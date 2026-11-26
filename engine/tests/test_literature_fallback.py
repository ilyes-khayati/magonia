import io
import json
from urllib.error import HTTPError

import pytest

from engine import literature


def crossref_reply():
    item = {
        "DOI": "10.1000/ABC",
        "title": ["Drought and olive groves in Tunisia"],
        "author": [{"given": "A.", "family": "Ali"}],
        "issued": {"date-parts": [[2021, 3]]},
        "container-title": ["Some Journal"],
        "abstract": "<jats:p>Abstract NDVI fell in dry years.</jats:p>",
        "is-referenced-by-count": 7,
    }
    return io.BytesIO(json.dumps({"message": {"items": [item]}}).encode())


def test_when_openalex_is_out_of_budget_crossref_is_searched(monkeypatch):
    def fake(request, timeout, context):
        if "openalex" in request.full_url:
            raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
        return crossref_reply()

    monkeypatch.setattr(literature, "urlopen", fake)
    [paper] = literature.search_papers("olive drought NDVI")
    assert paper.id == "doi:10.1000/abc" and paper.year == 2021
    assert paper.abstract == "NDVI fell in dry years." and paper.short == "Ali, 2021"


def test_without_the_backup_the_researcher_is_told_the_limit(monkeypatch):
    def fake(request, timeout, context):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(literature, "urlopen", fake)
    with pytest.raises(literature.LiteratureError, match="daily limit"):
        literature.search_papers("olive drought NDVI")
    with pytest.raises(literature.LiteratureError, match="daily limit"):
        literature.search_papers("olive drought NDVI", fallback=False)
