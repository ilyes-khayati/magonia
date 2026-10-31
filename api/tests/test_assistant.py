import json
import sqlite3

import pytest
from engine import assistant as engine_assistant
from engine.assistant import ProviderError, Scripted, ToolCall
from engine.literature import Paper

from api import main
from api.store import Store


class Unreachable:
    name = "unreachable"

    def stream(self, messages, tools=None):
        raise ProviderError("Could not reach the language model. Is Ollama running?")
        yield


def paper(surname, year):
    return Paper(
        id="W1",
        title="A study",
        authors=[f"A. {surname}"],
        year=year,
        venue="Journal",
        doi="10.1/x",
        abstract="An abstract.",
        open_access_url=None,
        cited_by=3,
        countries=["TN"],
    )


@pytest.fixture
def model():
    fake = Scripted("NDVI measures how green the vegetation is.")
    main.app.dependency_overrides[main.get_provider] = lambda: fake
    return fake


@pytest.fixture
def library(monkeypatch):
    """OpenAlex replaced by two fixed papers."""
    queries = []

    def search(query, question, keep=6, embed=None):
        queries.append(query)
        return [paper("Sghaier", 2022), paper("Crespo", 2025)]

    monkeypatch.setattr(engine_assistant, "find_papers", search)
    return queries


def workspace(client):
    return client.post("/workspaces", json={"name": "Jendouba"}).json()["id"]


def events(reply):
    return [json.loads(line) for line in reply.text.splitlines()]


def test_answer_streams_as_events_and_is_saved(client, model):
    ws = workspace(client)

    reply = client.post(f"/workspaces/{ws}/chat", json={"content": "What is NDVI?"})
    assert reply.status_code == 200
    got = events(reply)
    assert "".join(e["text"] for e in got if e["type"] == "text") == (
        "NDVI measures how green the vegetation is."
    )
    assert got[-1]["type"] == "check"

    saved = client.get(f"/workspaces/{ws}/messages").json()
    assert [(m["role"], m["content"]) for m in saved] == [
        ("user", "What is NDVI?"),
        ("assistant", "NDVI measures how green the vegetation is."),
    ]


def test_searched_answer_keeps_its_papers_and_check(client, library):
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought"}),
        "Drought lowers olive NDVI [1], see also [4].",
    )
    main.app.dependency_overrides[main.get_provider] = lambda: model
    ws = workspace(client)

    got = events(client.post(f"/workspaces/{ws}/chat", json={"content": "Drought and olives?"}))
    assert [e["type"] for e in got if e["type"] != "text"] == ["route", "search", "papers", "check"]
    assert library == ["olive drought"]

    answer = client.get(f"/workspaces/{ws}/messages").json()[-1]
    assert answer["content"] == "Drought lowers olive NDVI [1], see also."
    assert answer["details"]["searches"] == ["olive drought"]
    assert [p["short"] for p in answer["details"]["papers"]] == ["Sghaier, 2022", "Crespo, 2025"]
    assert answer["details"]["check"] == {"cited": [1], "removed": [4], "unverified": []}


def test_the_model_sees_the_earlier_conversation(client, model):
    ws = workspace(client)
    client.post(f"/workspaces/{ws}/chat", json={"content": "What is NDVI?"})
    client.post(f"/workspaces/{ws}/chat", json={"content": "And LST?"})

    assert [m["content"] for m in model.seen[1:]] == [
        "What is NDVI?",
        "NDVI measures how green the vegetation is.",
        "And LST?",
    ]


def test_conversations_belong_to_their_workspace(client, model):
    first, second = workspace(client), workspace(client)
    client.post(f"/workspaces/{first}/chat", json={"content": "What is NDVI?"})

    assert client.get(f"/workspaces/{second}/messages").json() == []
    assert client.delete(f"/workspaces/{first}/messages").status_code == 204
    assert client.get(f"/workspaces/{first}/messages").json() == []


def test_unreachable_model_is_a_503_and_nothing_is_saved(client):
    main.app.dependency_overrides[main.get_provider] = lambda: Unreachable()
    ws = workspace(client)

    reply = client.post(f"/workspaces/{ws}/chat", json={"content": "What is NDVI?"})
    assert reply.status_code == 503
    assert "Is Ollama running" in reply.json()["detail"]
    assert client.get(f"/workspaces/{ws}/messages").json() == []


def test_empty_questions_and_unknown_workspaces_are_refused(client, model):
    ws = workspace(client)
    assert client.post(f"/workspaces/{ws}/chat", json={"content": ""}).status_code == 422
    assert client.post("/workspaces/999/chat", json={"content": "Hi"}).status_code == 404


def test_assistant_reports_its_name_and_model(client, model):
    assert client.get("/assistant").json() == {"name": "Magonia", "model": "scripted"}


def test_database_from_version_1_2_is_upgraded(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE workspaces (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
        "settings TEXT NOT NULL DEFAULT '{}', created TEXT NOT NULL, updated TEXT NOT NULL);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id INTEGER NOT "
        "NULL, role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL);"
        "INSERT INTO workspaces (name, created, updated) VALUES ('w', 'x', 'x');"
        "INSERT INTO messages (workspace_id, role, content, created) VALUES (1, 'user', 'hi', 'x');"
    )
    old.commit()
    old.close()

    store = Store(path)
    assert store.messages(1)[0]["details"] == {}
    assert store.add_message(1, "assistant", "hello", {"searches": ["q"]})["details"] == {
        "searches": ["q"]
    }


def series_options(area_id, variable="ndvi"):
    return {
        "area_id": area_id,
        "variable": variable,
        "start": "2020-01-01",
        "end": "2022-01-01",
        "masking": "pixel",
        "resolution": "monthly",
        "max_gap": 2,
    }


def test_the_model_reads_the_open_workspace_from_the_cache(client, model, store):
    from conftest import SQUARE
    from engine.pipeline import Request

    from api.jobs import cache_key

    ws = workspace(client)
    area = client.post(
        f"/workspaces/{ws}/areas", json={"name": "Orchard", "geometry": SQUARE}
    ).json()
    ndvi, lst = series_options(area["id"]), series_options(area["id"], "lst")
    points = [
        {"date": f"{2020 + i // 12}-{i % 12 + 1:02d}-01", "value": 0.3 + 0.02 * (i % 12)}
        | {"sd": 0.01, "n_pixels": 10, "masked": False, "filled": False, "n_obs": 2, "n_valid": 2}
        for i in range(24)
    ]
    request = Request("ndvi", SQUARE, "2020-01-01", "2022-01-01", "pixel", None, "monthly", 2)
    store.save_result(
        cache_key(request),
        {
            "variable": "ndvi",
            "name": "NDVI",
            "units": "",
            "points": points,
            "warnings": [],
            "provenance": {},
        },
    )
    view = {"page": "charts", "charts": ["ndvi", "lst"], "analyses": [], "series": [ndvi, lst]}

    got = events(
        client.post(f"/workspaces/{ws}/chat", json={"content": "When does it peak?", "view": view})
    )

    assert got[1] == {"type": "view", "cards": ["NDVI chart"]}
    question = model.seen[-1]["content"]
    assert question.endswith("The researcher asks: When does it peak?")
    assert "The researcher is on the charts page." in question
    assert (
        "Areas: Orchard (" in question and "Period 2020-01 to 2021-12, monthly values" in question
    )
    assert "Still loading, so not described: Orchard LST." in question
    assert "peaks in Dec (0.52)" in question
    saved = client.get(f"/workspaces/{ws}/messages").json()
    assert saved[0]["content"] == "When does it peak?"  # the facts are not stored as the question
    assert saved[1]["details"]["cards"] == ["NDVI chart"]
    # the scripted answer has no numbers about the data, so the check is empty but saved
    assert saved[1]["details"]["numbers"] == []


def test_a_view_naming_another_workspaces_area_is_ignored(client, model):
    from conftest import SQUARE

    first, second = workspace(client), workspace(client)
    area = client.post(
        f"/workspaces/{first}/areas", json={"name": "Orchard", "geometry": SQUARE}
    ).json()
    view = {"series": [series_options(area["id"])]}
    client.post(f"/workspaces/{second}/chat", json={"content": "Hi", "view": view})
    assert "Orchard" not in model.seen[-1]["content"]
