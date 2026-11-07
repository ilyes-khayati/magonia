import pytest

from engine import layers
from engine.catalogue import CATALOGUE


def test_every_variable_has_a_colour_ramp():
    assert set(layers.LEGENDS) == set(CATALOGUE)
    for key, shown in layers.LEGENDS.items():
        assert shown.low < shown.high, key
        assert all(len(c) == 6 for c in shown.palette), key


def test_drought_is_drawn_around_zero():
    shown = layers.legend("spei").to_dict()
    assert shown["low"] == -shown["high"]
    assert shown["palette"][0] == "#a50026" and shown["palette"][-1] == "#313695"


def test_an_unknown_variable_is_refused():
    with pytest.raises(KeyError, match="unknown variable"):
        layers.legend("olives")


@pytest.mark.live
def test_a_month_of_ndvi_is_drawn_and_a_pixel_read():
    from engine.earth_engine import connect

    connect()
    assert "{z}" in layers.tiles("ndvi", "2020-03")["url"]
    points = layers.point_series("ndvi", 8.5605, 36.508, "2020-01-01", "2020-02-01")
    assert len(points) == 2 and all(0 < p["value"] < 1 for p in points)
    cells = layers.pixel_grid(
        "lst",
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [8.556, 36.505],
                    [8.566, 36.505],
                    [8.566, 36.512],
                    [8.556, 36.512],
                    [8.556, 36.505],
                ]
            ],
        },
    )
    assert 1 <= len(cells["features"]) <= 9


def test_earth_engine_failures_are_said_plainly():
    from engine.earth_engine import plainly

    busy = plainly(RuntimeError("Too many concurrent aggregations."), "draw NDVI")
    assert busy == "Earth Engine is busy and could not draw NDVI. Try again in a minute."
    assert "smaller area" in plainly(RuntimeError("Computation timed out."))
    assert "Traceback" not in plainly(RuntimeError("Traceback (most recent call last)"))
