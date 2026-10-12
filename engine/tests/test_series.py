import json
from pathlib import Path

import pandas as pd
import pytest

from engine.earth_engine import connect
from engine.series import ndvi_series, to_table

DATA = Path(__file__).parent / "data"
ORCHARD = DATA / "jendouba_orchard.geojson"
REFERENCE = DATA / "reference_ndvi_16day.csv"  # extracted independently for the 2026 paper


def properties(ndvi, quality=0, sd=500, n_pixels=20):
    values = {"date": "2023-01-01", "sd": sd, "n_pixels": n_pixels, "quality": quality}
    if ndvi is not None:  # Earth Engine drops a property when its value is null
        values["ndvi"] = ndvi
    return {"properties": values}


def test_to_table_scales_and_parses_dates():
    table = to_table([properties(5804)])
    assert table["date"][0] == pd.Timestamp("2023-01-01")
    assert table["ndvi"][0] == pytest.approx(0.5804)
    assert table["sd"][0] == pytest.approx(0.05)
    assert table["n_pixels"][0] == 20
    assert not table["masked"][0]


def test_date_with_no_clean_pixels_is_masked():
    table = to_table([{"properties": {"date": "2023-01-01", "n_pixels": 0, "quality": 3}}])
    assert table["masked"][0]
    assert table["ndvi"].isna().all()
    assert table["n_pixels"][0] == 0


def test_date_masking_drops_cloudy_dates():
    features = [properties(5804, quality=0), properties(2300, quality=3)]
    table = to_table(features, masking="date")
    assert list(table["masked"]) == [False, True]
    assert table["n_pixels"][1] == 0


def test_no_masking_keeps_cloudy_dates():
    table = to_table([properties(2300, quality=3)], masking="none")
    assert table["ndvi"][0] == pytest.approx(0.23)


def test_to_table_handles_no_images():
    table = to_table([])
    assert list(table.columns) == ["date", "ndvi", "sd", "n_pixels", "masked"]
    assert table.empty


def test_unknown_masking_is_rejected():
    with pytest.raises(ValueError, match="masking"):
        ndvi_series({}, "2023-01-01", "2024-01-01", masking="clouds")


@pytest.mark.live
def test_live_orchard_2023():
    connect()
    geometry = json.loads(ORCHARD.read_text())["features"][0]["geometry"]
    table = ndvi_series(geometry, "2023-01-01", "2024-01-01")
    assert len(table) == 23
    assert table["ndvi"].dropna().between(0, 1).all()


@pytest.mark.live
def test_live_matches_the_reference_extraction():
    connect()
    geometry = json.loads(ORCHARD.read_text())["features"][0]["geometry"]
    table = ndvi_series(geometry, "2000-03-01", "2025-01-01", masking="date")
    reference = pd.read_csv(REFERENCE, parse_dates=["date"])

    assert list(table["date"]) == list(reference["date"])
    assert list(table["masked"]) == list(reference["NDVI"].isna())
    assert table["ndvi"].to_numpy() == pytest.approx(
        reference["NDVI"].to_numpy(), abs=1e-6, nan_ok=True
    )
