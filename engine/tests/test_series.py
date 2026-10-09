import json
from pathlib import Path

import pandas as pd
import pytest

from engine.earth_engine import connect
from engine.series import ndvi_series, to_table

ORCHARD = Path(__file__).parent / "data" / "jendouba_orchard.geojson"


def test_to_table_scales_and_parses_dates():
    table = to_table([{"properties": {"date": "2023-01-01", "ndvi": 5804}}])
    assert table["date"][0] == pd.Timestamp("2023-01-01")
    assert table["ndvi"][0] == pytest.approx(0.5804)


def test_to_table_marks_missing_values():
    # Earth Engine drops a property when its value is null (e.g. no valid pixels)
    table = to_table([{"properties": {"date": "2023-01-01"}}])
    assert table["ndvi"].isna().all()


def test_to_table_handles_no_images():
    table = to_table([])
    assert list(table.columns) == ["date", "ndvi"]
    assert table.empty


@pytest.mark.live
def test_live_orchard_2023():
    connect()
    geometry = json.loads(ORCHARD.read_text())["features"][0]["geometry"]
    table = ndvi_series(geometry, "2023-01-01", "2024-01-01")
    assert len(table) == 23
    assert table["ndvi"].between(0, 1).all()
    