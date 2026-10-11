from pathlib import Path

import pytest

from engine.areas import AreaError, load_areas, make_area
from engine.earth_engine import connect

ORCHARD = Path(__file__).parent / "data" / "jendouba_orchard.geojson"

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[8, 36], [8.01, 36], [8.01, 36.01], [8, 36.01], [8, 36]]],
}
BOWTIE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


def feature(geometry, name=None):
    return {"type": "Feature", "properties": {"name": name} if name else {}, "geometry": geometry}


def test_orchard_area_matches_the_field_survey():
    [orchard] = load_areas(ORCHARD)
    assert orchard.name == "Area 1"
    assert orchard.area_km2 == pytest.approx(0.644, abs=0.001)


def test_several_named_areas():
    collection = {
        "type": "FeatureCollection",
        "features": [feature(SQUARE, "north"), feature(SQUARE)],
    }
    assert [area.name for area in load_areas(collection)] == ["north", "Area 2"]


def test_bare_geometry_is_one_area():
    assert len(load_areas(SQUARE)) == 1


def test_self_intersecting_polygon_is_rejected():
    with pytest.raises(AreaError, match="Self-intersection"):
        make_area(BOWTIE, "bowtie")


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"type": "Point", "coordinates": [8, 36]}, "expected a Polygon"),
        (None, "expected a Polygon"),
        ({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]}, "Too few points"),
        ({"type": "Polygon", "coordinates": "8 36"}, "unreadable"),
        ({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [2, 2], [0, 0]]]}, "invalid polygon"),
        (
            {
                "type": "Polygon",
                "coordinates": [
                    [[500000, 4000000], [500100, 4000000], [500100, 4000100], [500000, 4000000]]
                ],
            },
            "longitude",
        ),
    ],
)
def test_unusable_geometries_are_rejected(geometry, message):
    with pytest.raises(AreaError, match=message):
        make_area(geometry, "bad")


def test_duplicate_names_are_rejected():
    collection = {
        "type": "FeatureCollection",
        "features": [feature(SQUARE, "a"), feature(SQUARE, "a")],
    }
    with pytest.raises(AreaError, match="unique: a"):
        load_areas(collection)


def test_empty_collection_is_rejected():
    with pytest.raises(AreaError, match="no areas"):
        load_areas({"type": "FeatureCollection", "features": []})


@pytest.mark.live
def test_live_earth_engine_measures_the_same_area():
    connect()
    [orchard] = load_areas(ORCHARD)
    area_km2 = orchard.to_ee().area(maxError=1).getInfo() / 1e6
    assert area_km2 == pytest.approx(orchard.area_km2, rel=0.001)
