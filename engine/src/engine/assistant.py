"""The Magonia assistant: its rules, and the language models it can talk through."""

import json
import os
from collections.abc import Iterator
from typing import Literal, Protocol, TypedDict
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

NAME = "Magonia"

RULES = f"""You are {NAME}, the research assistant inside the Magonia platform, which researchers \
use to study vegetation, land surface temperature and drought from satellite data.

- Help only with agricultural and environmental remote sensing, and the statistics and \
methods around it. Politely decline anything else.
- Never invent a reference, a number or a result. If you do not know, say so.
- Say how sure you are, and say when evidence is thin or studies disagree.
- Be concise and plain. Researchers are busy.

Facts about yourself (state only these; do not guess beyond them):
- Magonia was built by Ilyes Khayati as an engineering capstone project.
- This conversation is saved in the researcher's current workspace and continues when they \
come back. Earlier messages in it are shown to you.
- You cannot yet see the areas, variables or results open in Magonia, and you cannot yet \
search the literature. Both are coming. Until then, ask the researcher to share the numbers \
they want to discuss."""


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class ProviderError(Exception):
    """The language model could not be reached or refused the request."""


class Provider(Protocol):
    """Anything that turns a conversation into the next answer, a piece at a time."""

    name: str

    def stream(self, messages: list[Message]) -> Iterator[str]: ...


class Ollama:
    """A model served by Ollama, on this computer or another one on the network."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.url = url.rstrip("/")
        self.model = model
        self.name = f"{model} (Ollama)"

    def stream(self, messages: list[Message]) -> Iterator[str]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": RULES}, *messages],
            "stream": True,
        }
        request = Request(
            f"{self.url}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=120)
        except URLError as exc:
            raise ProviderError(
                f"Could not reach the language model at {self.url}. Is Ollama running?"
            ) from exc
        # Ollama sends one JSON object per line, each with the next piece of the answer
        with response:
            for line in response:
                piece = json.loads(line)
                if "error" in piece:
                    raise ProviderError(piece["error"])
                if text := piece.get("message", {}).get("content"):
                    yield text


class Scripted:
    """Answers with fixed text, word by word: for tests, and for trying the interface offline."""

    def __init__(self, answer: str = "This is a scripted answer."):
        self.answer = answer
        self.name = "scripted"

    def stream(self, messages: list[Message]) -> Iterator[str]:
        for i, word in enumerate(self.answer.split(" ")):
            yield word if i == 0 else f" {word}"


def from_environment() -> Provider:
    """The provider named by MAGONIA_MODEL_URL and MAGONIA_MODEL, in the environment or .env."""
    load_dotenv()
    url = os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434")
    if url == "scripted":
        return Scripted()
    return Ollama(url, os.environ.get("MAGONIA_MODEL", "qwen2.5:7b"))
