import pytest
from engine.earth_engine import EarthEngineError

from api import main


def answering(project=None):
    if project not in (None, "my-project"):
        raise EarthEngineError(f"Earth Engine project '{project}' did not answer")
    return project or "from-env"


@pytest.fixture(autouse=True)
def fake_check(monkeypatch):
    monkeypatch.setattr(main, "check", answering)


def test_status_uses_the_environment_by_default(client):
    assert client.get("/earth-engine").json() == {
        "connected": True,
        "project": "from-env",
        "error": None,
    }


def test_saving_a_working_project(client, store):
    response = client.put("/earth-engine", json={"project": "my-project"})
    assert response.json()["connected"]
    assert store.setting("ee_project") == "my-project"
    assert client.get("/earth-engine").json()["project"] == "my-project"


def test_a_project_that_does_not_answer_is_not_saved(client, store):
    response = client.put("/earth-engine", json={"project": "wrong-id"})
    assert response.status_code == 422
    assert "did not answer" in response.json()["detail"]
    assert store.setting("ee_project") is None


def test_status_reports_the_problem(client, store):
    store.set_setting("ee_project", "wrong-id")
    status = client.get("/earth-engine").json()
    assert not status["connected"]
    assert status["project"] == "wrong-id"
    assert "did not answer" in status["error"]


def test_project_ids_are_checked(client):
    assert client.put("/earth-engine", json={"project": "Bad Id!"}).status_code == 422
