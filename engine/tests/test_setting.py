"""Reading where a study was made, and naming it when an answer uses it for the researcher's
area. The expectations for the real abstracts were written down before the reader ran on
them (16 Nov)."""

import json
from pathlib import Path

from engine.literature import Paper
from engine.setting import compare, name_settings, of_paper, of_workspace, read, where

DATA = Path(__file__).parent / "data"
ORCHARD = of_workspace(
    ["Areas: Orchard (0.64 km²).", "The areas lie near 36.51° N, 8.56° E."], ["Orchard"]
)


def paper(title: str, abstract: str = "") -> Paper:
    return Paper("W1", title, [], 2020, None, None, abstract, None, 0, [])


def test_the_orchard_is_placed_in_tunisia_and_the_mediterranean_on_tree_crops():
    assert ORCHARD.places == ["Tunisia"]
    assert ORCHARD.regions == {"the Mediterranean"}
    assert ORCHARD.covers == ["tree crops"]


# (query, elsewhere, first place or None, first vegetation or None), labelled before running
EXPECTED = {
    "NDVI drought monsoon India vegetation response SPEI": (True, "China", None),
    "olive orchard NDVI Spain drought": (False, None, "olive"),
    "olive Tunisia NDVI remote sensing": (False, "Tunisia", "olive"),
    "Loess Plateau grassland NDVI precipitation": (True, None, None),
    "global NDVI trend greening": (False, None, None),
    "random forest NDVI forecasting": (True, "Pakistan", "cereals"),
    "Sahel vegetation greening rainfall": (True, "Sahel", None),
    "maize yield NDVI Great Plains": (True, None, "maize"),
    "Mediterranean forest drought NDVI Spain": (True, None, "forest"),
    "Cerrado Brazil NDVI seasonality": (True, "Brazil", None),
}


def test_real_abstracts_are_read_as_labelled_before_running():
    for item in json.loads((DATA / "setting_abstracts.json").read_text()):
        elsewhere, place, cover = EXPECTED[item["q"]]
        found = of_paper(paper(item["title"], item["abstract"]))
        assert compare(found, ORCHARD).elsewhere is elsewhere, item["q"]
        if place:
            assert place in found.places, (item["q"], found.places)
        if cover:
            assert found.covers[0] == cover, (item["q"], found.covers)


def test_a_model_called_random_forest_is_not_a_forest():
    assert "forest" not in read("NDVI forecast with Random Forest and an isolation forest").covers


def test_the_indian_ocean_is_not_india():
    assert read("Rainfall over the Indian Ocean and the Mediterranean").places == []


def test_a_monsoon_climate_differs_from_the_mediterranean():
    found = read("Vegetation responds to monsoon rainfall with a delay of two months.")
    assert compare(found, ORCHARD).differs == ["in a monsoon climate"]


def test_the_setting_is_named_after_the_citation_of_a_paper_made_elsewhere():
    india = compare(read("Rice in central India under the monsoon."), ORCHARD)
    tunisia = compare(read("Olive groves in Tunisia."), ORCHARD)
    text = (
        "NDVI falls a few months after a drought [1]. "
        "Olive canopies change little through the year [2]."
    )
    out, added = name_settings(text, {1: india, 2: tunisia})
    assert out == (
        "NDVI falls a few months after a drought [1] (found in India, on rice). "
        "Olive canopies change little through the year [2]."
    )
    assert added[0]["cites"] == [1]


def test_a_sentence_that_already_says_where_is_left_alone():
    india = compare(read("Rice in central India under the monsoon."), ORCHARD)
    text = "In India, NDVI falls a few months after a drought [1, p. 3]."
    assert name_settings(text, {1: india}) == (text, [])


def test_where_is_the_mean_of_the_outlines():
    square = {"type": "Polygon", "coordinates": [[[8, 36], [9, 36], [9, 37], [8, 37], [8, 36]]]}
    assert where([square]) == "The areas lie near 36.40° N, 8.40° E."
