import json
from pathlib import Path

import pandas as pd
import pytest

from engine.catalogue import LST, NDVI, SPEI
from engine.earth_engine import connect
from engine.series import series, size_warnings, to_table

DATA = Path(__file__).parent / "data"
ORCHARD = DATA / "jendouba_orchard.geojson"
# Extracted independently for the 2026 paper
REFERENCES = {
    "ndvi": (DATA / "reference_ndvi_16day.csv", "NDVI", "date"),
    "lst": (DATA / "reference_lst_8day.csv", "LST", "none"),
}


def properties(value, flagged=0, sd=500, n_pixels=20):
    values = {"date": "2023-01-01", "sd": sd, "n_pixels": n_pixels, "flagged": flagged}
    if value is not None:  # Earth Engine drops a property when its value is null
        values["value"] = value
    return {"properties": values}


def orchard():
    return json.loads(ORCHARD.read_text())["features"][0]["geometry"]


def test_to_table_scales_and_parses_dates():
    table = to_table([properties(5804)], NDVI)
    assert table["date"][0] == pd.Timestamp("2023-01-01")
    assert table["value"][0] == pytest.approx(0.5804)
    assert table["sd"][0] == pytest.approx(0.05)
    assert table["n_pixels"][0] == 20
    assert not table["masked"][0]


def test_lst_is_in_celsius():
    table = to_table([properties(15000, sd=50)], LST)
    assert table["value"][0] == pytest.approx(26.85)
    assert table["sd"][0] == pytest.approx(1.0)


def test_date_with_no_clean_pixels_is_masked():
    table = to_table([{"properties": {"date": "2023-01-01", "n_pixels": 0, "flagged": 1}}], NDVI)
    assert table["masked"][0]
    assert table["value"].isna().all()
    assert table["n_pixels"][0] == 0


def test_date_masking_drops_mostly_flagged_dates():
    features = [properties(5804, flagged=0.4), properties(2300, flagged=0.5)]
    table = to_table(features, NDVI, masking="date")
    assert list(table["masked"]) == [False, True]
    assert table["n_pixels"][1] == 0


def test_no_masking_keeps_flagged_dates():
    table = to_table([properties(2300, flagged=1)], NDVI, masking="none")
    assert table["value"][0] == pytest.approx(0.23)


def test_to_table_handles_no_images():
    table = to_table([], NDVI)
    assert list(table.columns) == ["date", "value", "sd", "n_pixels", "masked"]
    assert table.empty


def test_unknown_masking_is_rejected():
    with pytest.raises(ValueError, match="masking"):
        series("ndvi", {}, "2023-01-01", "2024-01-01", masking="clouds")


@pytest.mark.parametrize("scale", [None, 0, 49])
def test_spei_needs_a_time_scale(scale):
    with pytest.raises(ValueError, match="between 1 and 48"):
        series("spei", {}, "2023-01-01", "2024-01-01", scale=scale)


def test_time_scale_only_applies_to_spei():
    with pytest.raises(ValueError, match="no time scale"):
        series("ndvi", {}, "2023-01-01", "2024-01-01", scale=3)


def test_spei_without_a_value_is_masked():
    table = to_table([{"properties": {"date": "2023-01-01", "n_pixels": 1}}], SPEI, "none")
    assert table["masked"][0]
    assert table["n_pixels"][0] == 0


def test_area_smaller_than_a_pixel_is_warned():
    assert size_warnings(NDVI, 0.644) == []
    [warning] = size_warnings(LST, 0.644)
    assert "0.64 km²" in warning and "1 km" in warning
    assert "grid cell" in size_warnings(SPEI, 5000)[0]


@pytest.mark.live
@pytest.mark.parametrize("scale", SPEI.scales)
def test_live_spei_matches_the_reference_extraction(scale):
    connect()
    table = series("spei", orchard(), "2000-03-01", "2025-01-01", scale=scale)
    reference = pd.read_csv(DATA / "reference_spei_monthly.csv", parse_dates=["date"])

    assert list(table["date"]) == list(reference["date"])
    expected = reference[f"SPEI_{scale}"].to_numpy()
    assert table["value"].to_numpy() == pytest.approx(expected, abs=1e-6)


@pytest.mark.live
def test_live_orchard_2023():
    connect()
    table = series("ndvi", orchard(), "2023-01-01", "2024-01-01")
    assert len(table) == 23
    assert table["value"].dropna().between(0, 1).all()


@pytest.mark.live
@pytest.mark.parametrize("key", REFERENCES)
def test_live_matches_the_reference_extraction(key):
    path, column, masking = REFERENCES[key]
    connect()
    table = series(key, orchard(), "2000-03-01", "2025-01-01", masking)
    reference = pd.read_csv(path, parse_dates=["date"])

    assert list(table["date"]) == list(reference["date"])
    assert list(table["masked"]) == list(reference[column].isna())
    expected = reference[column].to_numpy()
    assert table["value"].to_numpy() == pytest.approx(expected, abs=1e-6, nan_ok=True)
