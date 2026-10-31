import pytest
from engine.library import Library
from fastapi.testclient import TestClient

from api import jobs, main
from api.store import Store

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[8.55, 36.50], [8.56, 36.50], [8.56, 36.51], [8.55, 36.51], [8.55, 36.50]]],
}


class Immediately:
    """Runs a job as soon as it is submitted, so tests need not wait."""

    def submit(self, work, *args):
        work(*args)


class EarthEngine:
    """Stands in for Earth Engine and counts the calls it receives."""

    def __init__(self):
        self.calls = 0

    def fetch(self, key, geometry, start, end, masking, scale):
        self.calls += 1
        return [
            {"properties": {"date": "2023-01-01", "value": 5800, "sd": 500, "n_pixels": 18}},
            {"properties": {"date": "2023-01-17", "n_pixels": 0}},
            {"properties": {"date": "2023-02-02", "value": 6000, "sd": 500, "n_pixels": 18}},
        ]


@pytest.fixture
def earth_engine(monkeypatch):
    fake = EarthEngine()
    monkeypatch.setattr(jobs, "connect", lambda project=None: "test-project")
    monkeypatch.setattr(jobs, "fetch", fake.fetch)
    return fake


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "magonia.db")


@pytest.fixture
def client(store, earth_engine, tmp_path):
    main.app.dependency_overrides[main.get_store] = lambda: store
    main.app.dependency_overrides[main.get_library] = lambda: Library(tmp_path / "library.db")
    main.app.dependency_overrides[main.get_runner] = lambda: Immediately()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
