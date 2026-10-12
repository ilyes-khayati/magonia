import pandas as pd
import pytest
from engine.earth_engine import EarthEngineError
from fastapi.testclient import TestClient

from api import main

REQUEST = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[8.70, 36.50], [8.71, 36.50], [8.71, 36.51], [8.70, 36.50]]],
    },
    "start": "2023-01-01",
    "end": "2024-01-01",
}


def fake_series(key, geometry, start, end, masking, scale):
    if key == "spei" and scale is None:
        raise ValueError("SPEI needs a time scale between 1 and 48 months")
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-01", "2023-01-17"]),
            "value": [0.58, float("nan")],
            "sd": [0.05, float("nan")],
            "n_pixels": [18, 0],
            "masked": [False, True],
        }
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "connect", lambda: "test-project")
    monkeypatch.setattr(main, "series", fake_series)
    return TestClient(main.app)


def test_series_returns_one_point_per_date(client):
    response = client.post("/series", json=REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["variable"] == "ndvi"
    assert body["points"][0] == {
        "date": "2023-01-01",
        "value": 0.58,
        "sd": 0.05,
        "n_pixels": 18,
        "masked": False,
        "filled": False,
        "n_obs": 1,
        "n_valid": 1,
    }
    assert body["points"][1]["value"] is None  # a gap at the end is never filled


def test_monthly_resolution(client):
    response = client.post("/series", json={**REQUEST, "resolution": "monthly"})
    [january] = response.json()["points"]
    assert january["date"] == "2023-01-01"
    assert (january["n_obs"], january["n_valid"]) == (2, 1)


def test_lst_reports_units_and_pixel_size_warning(client):
    response = client.post("/series", json={**REQUEST, "variable": "lst"})
    body = response.json()
    assert body["units"] == "°C"
    assert "smaller than one 1 km pixel" in body["warnings"][0]


def test_spei_is_named_after_its_time_scale(client):
    response = client.post("/series", json={**REQUEST, "variable": "spei", "scale": 12})
    body = response.json()
    assert body["name"] == "SPEI-12"
    assert "grid cell" in body["warnings"][0]


def test_spei_without_a_time_scale_is_rejected(client):
    response = client.post("/series", json={**REQUEST, "variable": "spei"})
    assert response.status_code == 422
    assert "time scale" in response.json()["detail"]


def test_invalid_polygon_is_rejected(client):
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    response = client.post("/series", json={**REQUEST, "geometry": bowtie})
    assert response.status_code == 422
    assert "Self-intersection" in response.json()["detail"]


@pytest.mark.parametrize(
    "field",
    [
        {"masking": "clouds"},
        {"variable": "rainfall"},
        {"variable": "spei", "scale": 60},
        {"resolution": "weekly"},
        {"max_gap": -1},
    ],
)
def test_unknown_options_are_rejected(client, field):
    response = client.post("/series", json={**REQUEST, **field})
    assert response.status_code == 422


def test_end_before_start_is_rejected(client):
    response = client.post("/series", json={**REQUEST, "end": "2022-01-01"})
    assert response.status_code == 422


def test_earth_engine_unavailable(monkeypatch):
    def fail():
        raise EarthEngineError("No Earth Engine project set.")

    monkeypatch.setattr(main, "connect", fail)
    response = TestClient(main.app).post("/series", json=REQUEST)
    assert response.status_code == 503
    assert "Earth Engine" in response.json()["detail"]
