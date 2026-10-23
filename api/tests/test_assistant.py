import pytest
from engine.assistant import ProviderError, Scripted

from api import main


class Unreachable:
    name = "unreachable"

    def stream(self, messages):
        raise ProviderError("Could not reach the language model. Is Ollama running?")
        yield


class Recorder(Scripted):
    """Remembers the conversation it was given."""

    def stream(self, messages):
        self.seen = messages
        return super().stream(messages)


@pytest.fixture
def model():
    fake = Recorder("NDVI measures how green the vegetation is.")
    main.app.dependency_overrides[main.get_provider] = lambda: fake
    return fake


def workspace(client):
    return client.post("/workspaces", json={"name": "Jendouba"}).json()["id"]


def test_answer_streams_and_conversation_is_saved(client, model):
    ws = workspace(client)

    reply = client.post(f"/workspaces/{ws}/chat", json={"content": "What is NDVI?"})
    assert reply.status_code == 200
    assert reply.text == "NDVI measures how green the vegetation is."

    saved = client.get(f"/workspaces/{ws}/messages").json()
    assert [(m["role"], m["content"]) for m in saved] == [
        ("user", "What is NDVI?"),
        ("assistant", "NDVI measures how green the vegetation is."),
    ]


def test_the_model_sees_the_earlier_conversation(client, model):
    ws = workspace(client)
    client.post(f"/workspaces/{ws}/chat", json={"content": "What is NDVI?"})
    client.post(f"/workspaces/{ws}/chat", json={"content": "And LST?"})

    assert [m["content"] for m in model.seen] == [
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
