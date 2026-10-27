"""The Magonia assistant: its rules, the language models it can talk through, and its tools."""

import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from engine.citations import check
from engine.literature import LiteratureError, Paper, search_papers

NAME = "Magonia"

RULES = f"""You are {NAME}, the research assistant inside the Magonia platform, which researchers \
use to study vegetation, land surface temperature and drought from satellite data.

- Help only with agricultural and environmental remote sensing, and the statistics and \
methods around it. Politely decline anything else.
- Never invent a reference, a number or a result. If you do not know, say so.
- Say how sure you are, and say when evidence is thin or studies disagree.
- Be concise and plain. Researchers are busy.

The literature:
- When a question is about what research has found, call search_papers first, with short \
English keywords. You may search again with different keywords if the first results miss.
- Base what you say about research only on the papers the search returns, and cite them by \
their number in square brackets, like [1] or [2, 4]. Cite nothing else, and never cite \
papers from memory.
- If the papers found do not answer the question, say so plainly instead of filling the gap.

Facts about yourself (state only these; do not guess beyond them):
- Magonia was built by Ilyes Khayati as an engineering capstone project.
- This conversation is saved in the researcher's current workspace and continues when they \
come back. Earlier messages in it are shown to you.
- You can search the literature through OpenAlex. You cannot yet read full papers, only \
titles and abstracts, and you cannot yet see the areas, variables or results open in \
Magonia. Both are coming. Until then, ask the researcher to share the numbers they want to \
discuss."""

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_papers",
        "description": (
            "Search the scholarly literature (OpenAlex) for papers on a topic. Returns numbered "
            "papers with title, authors, year and abstract."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Short English keywords"},
            },
            "required": ["query"],
        },
    },
}

Message = dict[str, Any]  # {"role": "user" | "assistant" | "tool", "content": ..., ...}


@dataclass
class ToolCall:
    name: str
    arguments: dict


class ProviderError(Exception):
    """The language model could not be reached or refused the request."""


class Provider(Protocol):
    """Anything that turns a conversation into the next answer, a piece at a time.

    Pieces are text, or a ToolCall when the model asks for a tool instead of answering.
    """

    name: str

    def stream(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Iterator[str | ToolCall]: ...


class Ollama:
    """A model served by Ollama, on this computer or another one on the network."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.url = url.rstrip("/")
        self.model = model
        self.name = f"{model} (Ollama)"

    def stream(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Iterator[str | ToolCall]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": RULES}, *messages],
            "stream": True,
            "options": {"num_ctx": 8192},  # room for the abstracts of the papers found
        }
        if tools:
            body["tools"] = tools
        request = Request(
            f"{self.url}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=300)
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
                message = piece.get("message", {})
                for call in message.get("tool_calls") or []:
                    yield ToolCall(
                        call["function"]["name"], call["function"].get("arguments") or {}
                    )
                if text := message.get("content"):
                    yield text


class Scripted:
    """Plays fixed steps, one per call: text (streamed word by word) or a ToolCall.

    For tests, and for trying the interface without a model.
    """

    def __init__(self, *steps: str | ToolCall):
        self.steps = list(steps) or ["This is a scripted answer."]
        self.calls = 0
        self.name = "scripted"
        self.seen: list[Message] = []

    def stream(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Iterator[str | ToolCall]:
        self.seen = messages
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        if isinstance(step, ToolCall):
            yield step
            return
        for i, word in enumerate(step.split(" ")):
            yield word if i == 0 else f" {word}"


def from_environment() -> Provider:
    """The provider named by MAGONIA_MODEL_URL and MAGONIA_MODEL, in the environment or .env."""
    load_dotenv()
    url = os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434")
    if url == "scripted":
        return Scripted()
    return Ollama(url, os.environ.get("MAGONIA_MODEL", "qwen2.5:7b"))


def for_the_model(papers: list[Paper], first: int) -> str:
    """Numbered papers as the model reads them; abstracts are shortened to save context."""
    if not papers:
        return "No papers were found. Try other keywords, or say that nothing was found."
    lines = ["Papers found. Cite them by number, e.g. [1]."]
    for n, paper in enumerate(papers, start=first):
        summary = (paper.abstract or "No abstract available.")[:700]
        lines.append(f"[{n}] {paper.short}. {paper.title}. {paper.venue or ''}\n{summary}")
    return "\n\n".join(lines)


def answer(
    provider: Provider,
    conversation: list[Message],
    search: Callable[[str], list[Paper]] | None = None,
    max_searches: int = 2,
) -> Iterator[dict]:
    """Answer the last message of the conversation, searching the literature when the model asks.

    Yields events for the interface: text pieces, searches, the papers found, and at the end
    the citation check, whose text replaces the streamed answer.
    """
    search = search or search_papers
    messages = list(conversation)
    papers: list[Paper] = []
    said: list[str] = []
    searches = 0
    while True:
        tools = [SEARCH_TOOL] if searches < max_searches else None
        calls = []
        for piece in provider.stream(messages, tools):
            if isinstance(piece, ToolCall):
                calls.append(piece)
            else:
                said.append(piece)
                yield {"type": "text", "text": piece}
        # Done when the model answered, or asked for a tool it was no longer offered
        if not calls or tools is None:
            break
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": c.name, "arguments": c.arguments}} for c in calls
                ],
            }
        )
        for call in calls:
            searches += 1
            query = str(call.arguments.get("query", "")).strip()
            if call.name != "search_papers" or not query:
                messages.append({"role": "tool", "content": "Unknown tool or empty query."})
                continue
            yield {"type": "search", "query": query}
            try:
                found = search(query)
            except LiteratureError as exc:
                yield {"type": "search_failed", "query": query, "error": str(exc)}
                messages.append({"role": "tool", "content": f"The search failed: {exc}"})
                continue
            first = len(papers) + 1
            papers.extend(found)
            yield {
                "type": "papers",
                "papers": [{"n": first + i, **p.to_dict()} for i, p in enumerate(found)],
            }
            messages.append({"role": "tool", "content": for_the_model(found, first)})

    verdict = check("".join(said), papers)
    yield {"type": "check", "text": verdict.text, **verdict.to_dict()}
