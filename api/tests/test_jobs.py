import threading
import time

import pytest
from conftest import SQUARE
from engine.earth_engine import EarthEngineError
from fastapi.testclient import TestClient

from api import jobs, main
from api.jobs import Runner

REQUEST = {"geometry": SQUARE, "start": "2023-01-01", "end": "2024-01-01"}


def test_finished_job_returns_the_series_with_provenance(client):
    job = client.post("/jobs", json=REQUEST).json()
    assert job["status"] == "done"
    result = client.get(f"/jobs/{job['id']}").json()["result"]
    assert [point["value"] for point in result["points"]] == pytest.approx([0.58, 0.59, 0.6])
    assert result["points"][1]["filled"]
    assert result["provenance"]["variable"]["key"] == "ndvi"


def test_identical_request_comes_from_the_cache(client, earth_engine):
    client.post("/jobs", json=REQUEST)
    again = client.post("/jobs", json=REQUEST).json()
    assert again["status"] == "done" and again["result"] is not None
    assert earth_engine.calls == 1


def test_changed_request_is_not_served_from_the_cache(client, earth_engine):
    client.post("/jobs", json=REQUEST)
    client.post("/jobs", json={**REQUEST, "max_gap": 0})
    assert earth_engine.calls == 2


def test_earth_engine_failure_is_readable(client, monkeypatch):
    def fail():
        raise EarthEngineError("No Earth Engine project set.")

    monkeypatch.setattr(jobs, "connect", fail)
    job = client.post("/jobs", json=REQUEST).json()
    assert job["status"] == "failed"
    assert "Earth Engine project" in job["error"]


def test_unexpected_failure_is_readable(client, monkeypatch):
    def broken(*args):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(jobs, "fetch", broken)
    job = client.post("/jobs", json=REQUEST).json()
    assert job["status"] == "failed"
    assert "quota exceeded" in job["error"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"end": "2022-01-01"}, "end must be after start"),
        ({"geometry": None}, "area_id or a geometry"),
        (
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
                }
            },
            "Self-intersection",
        ),
        ({"variable": "spei"}, "time scale"),
    ],
)
def test_bad_requests_fail_before_earth_engine(client, earth_engine, change, message):
    response = client.post("/jobs", json={**REQUEST, **change})
    assert response.status_code == 422
    assert message in str(response.json()["detail"])
    assert earth_engine.calls == 0


@pytest.mark.parametrize(
    "field",
    [{"masking": "clouds"}, {"variable": "rainfall"}, {"resolution": "weekly"}, {"max_gap": -1}],
)
def test_unknown_options_are_rejected(client, field):
    assert client.post("/jobs", json={**REQUEST, **field}).status_code == 422


def test_unknown_job(client):
    assert client.get("/jobs/999").status_code == 404


def test_long_request_does_not_block_the_server(store, monkeypatch):
    release = threading.Event()

    def slow_fetch(*args):
        release.wait(timeout=10)
        return [{"properties": {"date": "2023-01-01", "value": 5800, "sd": 500, "n_pixels": 18}}]

    monkeypatch.setattr(jobs, "connect", lambda: "test-project")
    monkeypatch.setattr(jobs, "fetch", slow_fetch)
    main.app.dependency_overrides[main.get_store] = lambda: store
    main.app.dependency_overrides[main.get_runner] = lambda: runner
    runner = Runner()
    try:
        client = TestClient(main.app)
        job = client.post("/jobs", json=REQUEST).json()
        assert job["status"] in ("queued", "running")
        assert client.get("/health").status_code == 200  # the server still answers

        release.set()
        for _ in range(100):
            if client.get(f"/jobs/{job['id']}").json()["status"] == "done":
                break
            time.sleep(0.05)
        assert client.get(f"/jobs/{job['id']}").json()["status"] == "done"
    finally:
        main.app.dependency_overrides.clear()


def test_unfinished_jobs_fail_after_a_restart(tmp_path):
    from api.store import Store

    first = Store(tmp_path / "magonia.db")
    job_id = first.create_job({}, "key", None, None, "running")
    second = Store(tmp_path / "magonia.db")
    assert second.job(job_id)["status"] == "failed"
    assert "stopped" in second.job(job_id)["error"]
