import json
import sqlite3
from dataclasses import replace

import pytest
from engine import assistant as engine_assistant
from engine.assistant import ProviderError, Scripted, ToolCall
from engine.fulltext import Passage
from engine.library import Library
from engine.literature import Paper

from api import main
from api.store import Store


class Unreachable:
    name = "unreachable"

    def stream(self, messages, tools=None):
        raise ProviderError("Magon is not available right now.")
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


def conversation(client, ws=None):
    ws = ws if ws is not None else workspace(client)
    return client.post(f"/workspaces/{ws}/conversations").json()["id"]


def events(reply):
    return [json.loads(line) for line in reply.text.splitlines()]


def test_answer_streams_as_events_and_is_saved(client, model):
    c = conversation(client)

    reply = client.post(f"/conversations/{c}/chat", json={"content": "What is NDVI?"})
    assert reply.status_code == 200
    got = events(reply)
    assert "".join(e["text"] for e in got if e["type"] == "text") == (
        "NDVI measures how green the vegetation is."
    )
    assert got[-1]["type"] == "check"

    saved = client.get(f"/conversations/{c}/messages").json()
    assert [(m["role"], m["content"]) for m in saved] == [
        ("user", "What is NDVI?"),
        ("assistant", "NDVI measures how green the vegetation is."),
    ]


def test_searched_answer_keeps_its_papers_and_check(client, library):
    # the test papers are made up, so their statements are kept and only marked
    client.put("/assistant/settings", json={"claims": "mark"})
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought"}),
        "Drought lowers olive NDVI [1], see also [4].",
    )
    main.app.dependency_overrides[main.get_provider] = lambda: model
    c = conversation(client)

    got = events(client.post(f"/conversations/{c}/chat", json={"content": "Drought and olives?"}))
    assert [e["type"] for e in got if e["type"] != "text"] == [
        "route",
        "search",
        "papers",
        "verifying",
        "check",
    ]
    assert library == ["olive drought"]

    answer = client.get(f"/conversations/{c}/messages").json()[-1]
    assert answer["content"] == "Drought lowers olive NDVI [1], see also."
    assert answer["details"]["searches"] == ["olive drought"]
    assert [p["short"] for p in answer["details"]["papers"]] == ["Sghaier, 2022", "Crespo, 2025"]
    assert answer["details"]["check"] == {
        "cited": [1],
        "removed": [4],
        "unverified": [],
        "pages_removed": [],
    }


def test_open_access_papers_are_read_and_their_pages_checked(client, monkeypatch, tmp_path):
    first = replace(paper("Sghaier", 2022), id="W1", pdf_url="https://example.org/1.pdf")
    monkeypatch.setattr(engine_assistant, "find_papers", lambda query, question, **_: [first])
    passages = [Passage(6, "Rainfed olive groves lost NDVI within one season of drought. " * 5)]
    shelf = Library(tmp_path / "read.db", reader=lambda url: passages)
    main.app.dependency_overrides[main.get_library] = lambda: shelf
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought"}),
        "Rainfed groves lost NDVI [1, p. 6], not on page 9 [1, p. 9].",
    )
    main.app.dependency_overrides[main.get_provider] = lambda: model
    c = conversation(client)

    got = events(client.post(f"/conversations/{c}/chat", json={"content": "Drought and olives?"}))
    assert [e["type"] for e in got if e["type"] != "text"] == [
        "route",
        "search",
        "papers",
        "reading",
        "passages",
        "verifying",
        "check",
    ]
    assert "[1, p. 6] Rainfed olive groves" in model.seen[-1]["content"]
    answer = client.get(f"/conversations/{c}/messages").json()[-1]
    assert answer["content"] == "Rainfed groves lost NDVI [1, p. 6], not on page 9 [1]."
    assert answer["details"]["check"]["pages_removed"] == ["[1, p. 9]"]
    assert answer["details"]["read"] == {"1": "read"}
    assert answer["details"]["passages"][0]["page"] == 6
    # the statement is about what the passage says; without a judge it stays unclear
    assert answer["details"]["support"][0]["source"] == "[1, p. 6]"
    assert answer["details"]["support"][0]["status"] == "unclear"
    assert answer["details"]["faithfulness"] == 0.0


def test_the_model_sees_the_earlier_conversation(client, model):
    c = conversation(client)
    client.post(f"/conversations/{c}/chat", json={"content": "What is NDVI?"})
    client.post(f"/conversations/{c}/chat", json={"content": "And LST?"})

    assert [m["content"] for m in model.seen[1:]] == [
        "What is NDVI?",
        "NDVI measures how green the vegetation is.",
        "And LST?",
    ]


def test_a_follow_up_is_given_the_papers_cited_before(client, library):
    # the test papers are made up, so their statements are kept and only marked
    client.put("/assistant/settings", json={"claims": "mark"})
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought"}),
        "Drought lowers olive NDVI [1].",
        "That study was in Tunisia [1].",
    )
    main.app.dependency_overrides[main.get_provider] = lambda: model
    c = conversation(client)
    client.post(f"/conversations/{c}/chat", json={"content": "Drought and olives?"})
    got = events(client.post(f"/conversations/{c}/chat", json={"content": "Where was it?"}))

    # the earlier answer reads with names, and its paper can be cited again as [1]
    assert "Drought lowers olive NDVI (Sghaier, 2022)." in [m["content"] for m in model.seen]
    assert next(e for e in got if e["type"] == "papers")["papers"][0]["short"] == "Sghaier, 2022"
    assert got[-1]["cited"] == [1] and got[-1]["removed"] == []


def test_conversations_are_listed_named_and_kept_apart(client, model):
    ws = workspace(client)
    first, second = conversation(client, ws), conversation(client, ws)
    client.post(f"/conversations/{first}/chat", json={"content": "What is NDVI?"})

    assert client.get(f"/conversations/{second}/messages").json() == []
    listed = client.get(f"/workspaces/{ws}/conversations").json()
    # the one last spoken in comes first, shown by its first question until it is named
    assert [(c["id"], c["title"], c["first_question"], c["messages"]) for c in listed] == [
        (first, None, "What is NDVI?", 2),
        (second, None, None, 0),
    ]
    renamed = client.patch(f"/conversations/{first}", json={"title": "Index basics"}).json()
    assert renamed["title"] == "Index basics"
    other = workspace(client)
    assert client.get(f"/workspaces/{other}/conversations").json() == []


def test_a_deleted_conversation_can_be_restored(client, model):
    ws = workspace(client)
    c = conversation(client, ws)
    client.post(f"/conversations/{c}/chat", json={"content": "What is NDVI?"})

    assert client.delete(f"/conversations/{c}").status_code == 204
    assert client.get(f"/workspaces/{ws}/conversations").json() == []
    assert client.get(f"/conversations/{c}/messages").status_code == 404
    assert client.post(f"/conversations/{c}/chat", json={"content": "Hi"}).status_code == 404

    assert client.post(f"/conversations/{c}/restore").json()["messages"] == 2
    assert len(client.get(f"/conversations/{c}/messages").json()) == 2


def test_conversations_of_a_deleted_workspace_are_closed(client, model):
    ws = workspace(client)
    c = conversation(client, ws)
    client.delete(f"/workspaces/{ws}")
    assert client.get(f"/conversations/{c}/messages").status_code == 404
    client.post(f"/workspaces/{ws}/restore")
    assert client.get(f"/conversations/{c}/messages").json() == []


def test_unreachable_model_is_a_503_and_nothing_is_saved(client):
    main.app.dependency_overrides[main.get_provider] = lambda: Unreachable()
    c = conversation(client)

    reply = client.post(f"/conversations/{c}/chat", json={"content": "What is NDVI?"})
    assert reply.status_code == 503
    assert "not available right now" in reply.json()["detail"]
    assert client.get(f"/conversations/{c}/messages").json() == []


def test_empty_questions_and_unknown_workspaces_are_refused(client, model):
    c = conversation(client)
    assert client.post(f"/conversations/{c}/chat", json={"content": ""}).status_code == 422
    assert client.post("/conversations/999/chat", json={"content": "Hi"}).status_code == 404


def test_assistant_reports_its_name_and_model(client, model):
    assert client.get("/assistant").json() == {"name": "Magon", "model": "scripted"}


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
    # the workspace's one conversation became its first conversation
    [kept] = store.conversations(1)
    assert kept["first_question"] == "hi"
    assert store.messages(kept["id"])[0]["details"] == {}
    assert store.add_message(kept["id"], "assistant", "hello", {"searches": ["q"]})["details"] == {
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
    c = conversation(client, ws)
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
        client.post(
            f"/conversations/{c}/chat", json={"content": "When does it peak?", "view": view}
        )
    )

    assert got[1] == {"type": "view", "cards": ["NDVI chart"]}
    question = model.seen[-1]["content"]
    assert question.endswith("The researcher asks: When does it peak?")
    assert 'The researcher is in the workspace "Jendouba", on the charts page.' in question
    assert (
        "Areas: Orchard (" in question and "Period 2020-01 to 2021-12, monthly values" in question
    )
    assert "Still loading, so not described: Orchard LST." in question
    assert "peaks in Dec (0.52)" in question
    saved = client.get(f"/conversations/{c}/messages").json()
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
    c = conversation(client, second)
    client.post(f"/conversations/{c}/chat", json={"content": "Hi", "view": view})
    assert "Orchard" not in model.seen[-1]["content"]


def test_a_question_asked_from_a_card_is_about_that_card(client, model):
    c = conversation(client)
    view = {"page": "analyses", "focus": "Drought years (Trend 1)"}
    got = events(
        client.post(f"/conversations/{c}/chat", json={"content": "Is it real?", "view": view})
    )
    assert got[0]["kind"] == "data"  # not small talk, though it reads like it
    assert 'The question is about the card "Drought years (Trend 1)"' in model.seen[-1]["content"]


def test_magon_settings_are_saved_and_choose_the_model(client, monkeypatch):
    monkeypatch.setenv("MAGONIA_MODEL_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MAGONIA_MODEL", "qwen2.5:7b")
    first = client.get("/assistant/settings").json()
    assert (
        first["model"] is None and first["detail"] == "concise" and first["papers_per_search"] == 6
    )
    assert first["in_use"] == {"model_url": "http://127.0.0.1:9", "model": "qwen2.5:7b"}

    chosen = {"model": "qwen3:8b", "temperature": 0.2, "detail": "detailed", "papers_per_search": 8}
    assert client.put("/assistant/settings", json=chosen).status_code == 200
    again = client.get("/assistant/settings").json()
    assert again["in_use"]["model"] == "qwen3:8b"
    assert {k: again[k] for k in chosen} == chosen
    assert client.get("/assistant").json()["model"] == "qwen3:8b (Ollama)"

    assert client.put("/assistant/settings", json={"papers_per_search": 50}).status_code == 422
    assert client.put("/assistant/settings", json={"model_url": "not a url"}).status_code == 422
    assert client.put("/assistant/settings", json={"verifier": "oracle"}).status_code == 422


def test_the_chosen_verifier_checks_the_answer(client, monkeypatch, library):
    asked = []
    monkeypatch.setattr(main, "judge_for", lambda name: asked.append(name))
    main.app.dependency_overrides[main.get_provider] = lambda: Scripted("Fine.")
    assert client.get("/assistant/settings").json()["verifier"] == "model"
    client.put("/assistant/settings", json={"verifier": "nli"})
    wid = workspace(client)
    conversation = client.post(f"/workspaces/{wid}/conversations").json()["id"]
    client.post(f"/conversations/{conversation}/chat", json={"content": "What is NDVI?"})
    assert asked == ["nli"]


def test_an_unreachable_model_server_lists_no_models(client):
    found = client.get("/assistant/models", params={"url": "http://127.0.0.1:9"}).json()
    assert found["models"] == [] and "did not answer" in found["error"]


def test_the_chosen_answer_length_reaches_the_model(client, monkeypatch, library):
    seen = []

    class Recorder(Scripted):
        def stream(self, messages, tools=None):
            seen.append(messages[0]["content"])
            yield from super().stream(messages, tools)

    main.app.dependency_overrides[main.get_provider] = lambda: Recorder("Fine.")
    client.put("/assistant/settings", json={"detail": "detailed"})
    wid = workspace(client)
    conversation = client.post(f"/workspaces/{wid}/conversations").json()["id"]
    client.post(f"/conversations/{conversation}/chat", json={"content": "What is NDVI?"})
    assert "thorough" in seen[0]
