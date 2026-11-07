import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar

import pytest

from engine.assistant import (
    RULES,
    Ollama,
    ProviderError,
    Scripted,
    ToolCall,
    from_environment,
    installed_models,
)


def test_scripted_streams_the_answer_word_by_word():
    pieces = list(Scripted("NDVI measures greenness.").stream([]))
    assert pieces == ["NDVI", " measures", " greenness."]
    assert "".join(pieces) == "NDVI measures greenness."


class FakeOllama(BaseHTTPRequestHandler):
    """Answers /api/chat the way Ollama does: one JSON object per line."""

    received: ClassVar[dict] = {}

    def do_GET(self):  # /api/tags: the models installed
        self.send_response(200)
        self.end_headers()
        models = [
            {"name": "qwen2.5:7b"},
            {"name": "nomic-embed-text:latest"},
            {"name": "phi4-mini"},
        ]
        self.wfile.write(json.dumps({"models": models}).encode())

    def do_POST(self):
        FakeOllama.received = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()
        if FakeOllama.received.get("tools"):
            call = {"function": {"name": "search_papers", "arguments": {"query": "olive"}}}
            self.wfile.write(
                json.dumps({"message": {"content": "", "tool_calls": [call]}}).encode() + b"\n"
            )
        for piece in ["Hello", " there"]:
            self.wfile.write(json.dumps({"message": {"content": piece}}).encode() + b"\n")
        self.wfile.write(json.dumps({"done": True}).encode() + b"\n")

    def log_message(self, *args):
        pass


@pytest.fixture
def ollama_url():
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_ollama_sends_the_rules_first_and_streams_the_reply(ollama_url):
    model = Ollama(ollama_url, "test-model")
    reply = "".join(model.stream([{"role": "user", "content": "Hi"}]))

    assert reply == "Hello there"
    sent = FakeOllama.received
    assert sent["model"] == "test-model"
    assert sent["messages"][0] == {"role": "system", "content": RULES}
    assert sent["messages"][1] == {"role": "user", "content": "Hi"}


def test_unreachable_model_gives_a_clear_error():
    with pytest.raises(ProviderError, match="not available right now"):
        list(Ollama("http://127.0.0.1:9").stream([]))


def test_provider_is_chosen_from_the_environment(monkeypatch):
    monkeypatch.setenv("MAGONIA_MODEL_URL", "http://192.168.1.20:11434")
    monkeypatch.setenv("MAGONIA_MODEL", "qwen2.5:3b")
    provider = from_environment()
    assert isinstance(provider, Ollama)
    assert (provider.url, provider.model) == ("http://192.168.1.20:11434", "qwen2.5:3b")

    monkeypatch.setenv("MAGONIA_MODEL_URL", "scripted")
    assert isinstance(from_environment(), Scripted)


def test_ollama_passes_tool_calls_through(ollama_url):
    pieces = list(Ollama(ollama_url).stream([{"role": "user", "content": "Hi"}], tools=[{"x": 1}]))
    assert pieces[0] == ToolCall("search_papers", {"query": "olive"})
    assert FakeOllama.received["tools"] == [{"x": 1}]


def test_settings_choose_the_server_model_and_temperature(monkeypatch, ollama_url):
    monkeypatch.setenv("MAGONIA_MODEL_URL", "http://192.168.1.20:11434")
    provider = from_environment({"model_url": ollama_url, "model": "phi4-mini", "temperature": 0.2})
    assert (provider.url, provider.model) == (ollama_url, "phi4-mini")
    "".join(provider.stream([{"role": "user", "content": "Hi"}]))
    assert FakeOllama.received["options"]["temperature"] == 0.2
    # without a temperature the model keeps its own
    "".join(Ollama(ollama_url).stream([{"role": "user", "content": "Hi"}]))
    assert "temperature" not in FakeOllama.received["options"]


def test_the_models_listed_are_those_that_can_answer(ollama_url):
    assert installed_models(ollama_url) == ["phi4-mini", "qwen2.5:7b"]
