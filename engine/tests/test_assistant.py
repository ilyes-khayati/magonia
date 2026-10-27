import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar

import pytest

from engine.assistant import RULES, Ollama, ProviderError, Scripted, ToolCall, from_environment


def test_scripted_streams_the_answer_word_by_word():
    pieces = list(Scripted("NDVI measures greenness.").stream([]))
    assert pieces == ["NDVI", " measures", " greenness."]
    assert "".join(pieces) == "NDVI measures greenness."


class FakeOllama(BaseHTTPRequestHandler):
    """Answers /api/chat the way Ollama does: one JSON object per line."""

    received: ClassVar[dict] = {}

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
    with pytest.raises(ProviderError, match="Is Ollama running"):
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
