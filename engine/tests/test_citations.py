from engine.citations import check, numbers
from engine.literature import Paper


def paper(surname, year):
    return Paper(
        id="W1",
        title="t",
        authors=[f"A. {surname}", "B. Other", "C. Third"],
        year=year,
        venue=None,
        doi=None,
        abstract=None,
        open_access_url=None,
        cited_by=0,
        countries=[],
    )


THREE = [paper("Sghaier", 2022), paper("Crespo", 2025), paper("Daiz", 2026)]


def test_citation_groups_are_read():
    assert numbers("1") == [1]
    assert numbers("1, 3") == [1, 3]
    assert numbers("2-4") == [2, 3, 4]
    assert numbers("2–3, 5") == [2, 3, 5]


def test_valid_citations_are_kept_in_order_of_use():
    result = check("Drought lowers NDVI [2]. Irrigation helps [1, 3].", THREE)
    assert result.text == "Drought lowers NDVI [2]. Irrigation helps [1, 3]."
    assert result.cited == [2, 1, 3]
    assert result.removed == []


def test_invented_citation_is_removed_and_reported():
    result = check("Olive NDVI lags drought by two months [7].", THREE)
    assert result.text == "Olive NDVI lags drought by two months."
    assert result.removed == [7]
    assert result.cited == []


def test_mixed_group_keeps_only_the_real_papers():
    result = check("Several studies agree [1, 9, 3].", THREE)
    assert result.text == "Several studies agree [1, 3]."
    assert result.removed == [9]


def test_answer_without_any_search_can_cite_nothing():
    result = check("As shown before [1], drought matters [2].", [])
    assert result.text == "As shown before, drought matters."
    assert result.removed == [1, 2]


def test_author_year_mentions_are_flagged_unless_retrieved():
    result = check("This agrees with (Crespo et al., 2025) but not (Smith et al., 2019).", THREE)
    assert result.unverified == ["(Smith et al., 2019)"]
