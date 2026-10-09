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


def fake_series(geometry, start, end):
    return pd.DataFrame(
        {"date": pd.to_datetime(["2023-01-01", "2023-01-17"]), "ndvi": [0.58, float("nan")]}
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "connect", lambda: "test-project")
    monkeypatch.setattr(main, "ndvi_series", fake_series)
    return TestClient(main.app)


def test_series_returns_one_point_per_date(client):
    response = client.post("/series", json=REQUEST)
    assert response.status_code == 200
    assert response.json() == [
        {"date": "2023-01-01", "ndvi": 0.58},
        {"date": "2023-01-17", "ndvi": None},
    ]


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
