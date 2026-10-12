import ee
import pytest

from engine import earth_engine
from engine.earth_engine import EarthEngineError, check, connect


@pytest.fixture
def fake_ee(monkeypatch):
    """Replace Earth Engine and .env loading so tests never touch the network or local files."""
    calls = []
    monkeypatch.setattr(ee, "Initialize", lambda project: calls.append(project))
    monkeypatch.setattr(earth_engine, "load_dotenv", lambda: None)
    monkeypatch.delenv("EE_PROJECT", raising=False)
    return calls


def test_argument_wins_over_environment(fake_ee, monkeypatch):
    monkeypatch.setenv("EE_PROJECT", "from-env")
    assert connect("from-arg") == "from-arg"
    assert fake_ee == ["from-arg"]


def test_reads_project_from_environment(fake_ee, monkeypatch):
    monkeypatch.setenv("EE_PROJECT", "from-env")
    assert connect() == "from-env"


def test_missing_project_raises(fake_ee):
    with pytest.raises(EarthEngineError, match="EE_PROJECT"):
        connect()


def test_earth_engine_failure_is_explained(monkeypatch):
    def fail(project):
        raise ee.EEException("Please authorize access")

    monkeypatch.setattr(ee, "Initialize", fail)
    with pytest.raises(EarthEngineError, match="earthengine authenticate"):
        connect("some-project")


def test_check_reports_a_project_that_does_not_answer(fake_ee, monkeypatch):
    class Refusing:
        def getInfo(self):
            raise ee.EEException("Earth Engine API has not been used in project wrong-id")

    monkeypatch.setattr(ee, "Number", lambda value: Refusing())
    with pytest.raises(EarthEngineError, match="wrong-id"):
        check("wrong-id")


@pytest.mark.live
def test_live_connection():
    connect()
    assert ee.Number(1).add(1).getInfo() == 2
