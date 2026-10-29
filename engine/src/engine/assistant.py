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
from engine.facts import View
from engine.literature import LiteratureError, Paper, search_papers
from engine.numbers import check_numbers
from engine.proposals import PROPOSE_TOOL, ProposalError, proposal
from engine.proposals import describe as describe_proposal

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
titles and abstracts.
- You can see the areas, variables and analyses open in Magonia, as facts computed by code, \
when the researcher has some open. You cannot see the map or the charts as pictures, and \
you cannot run new analyses yet."""

# Sent with the facts only, so that questions asked without a workspace are not steered by them
MAX_PROPOSALS = 2

DATA_RULES = """How to use these facts:
- If the question is about the researcher's areas or results, answer from the facts. Copy \
numbers exactly as written, never compute new ones, and name the chart or analysis each \
number comes from, for example "(NDVI chart)".
- The facts do not contain the values of single months or years. When asked for them, call \
read_series (one area and variable, a year or every year) and quote what it returns. Never \
write a value you were not given.
- Interpret only what the facts state. A positive r means the two rise together. A trend \
that is not statistically significant is not evidence of a trend. A correlation beyond its \
chance band is unlikely to be chance.
- Whether two models agree, and which model leans most on what, is stated in the facts. \
Repeat those verdicts; never judge them yourself from the size of a number such as τ.
- When the researcher asks for an analysis, a forecast or another period, call \
propose_analysis. You cannot run anything yourself: never say an analysis was run or added; \
say it is proposed and that they can add it.
- Answer only the question asked, with the few facts it needs.
- Keep the researcher's data and published research apart: say which is which.
- If the question is about published research rather than these data, search the \
literature as usual."""

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

READ_TOOL = {
    "type": "function",
    "function": {
        "name": "read_series",
        "description": (
            "Read the researcher's own data for one area and variable: the monthly values of "
            "one year, or the annual means of every year when no year is given."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "area": {"type": "string", "description": "Area name, as in the facts"},
                "variable": {"type": "string", "description": "ndvi, lst or spei"},
                "year": {"type": "integer", "description": "A year, or leave out"},
            },
            "required": ["area", "variable"],
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
    view: View | None = None,
    max_reads: int = 3,
) -> Iterator[dict]:
    """Answer the last message of the conversation, using tools when the model asks.

    With a view, the facts about the researcher's open workspace go with the question and the
    model may read their series more closely. Yields events for the interface: what was read,
    text pieces, searches, the papers found, and at the end the check, whose text replaces the
    streamed answer: citations checked against the papers found and, when there was a
    workspace or papers, every number checked against what the model was given.
    """
    search = search or search_papers
    messages = list(conversation)
    # what the model is given, against which every number in its answer is checked
    sources = [("your question", str(conversation[-1]["content"]))]
    if view is not None:
        sources += [(fact.card, fact.text) for fact in view.facts()]
        sources += [("your workspace", line) for line in view.context]
        yield {"type": "view", "cards": view.cards()}
        last = messages[-1]
        # the question comes last, where a small model attends to it best
        question = f"{view.sheet()}\n\n{DATA_RULES}\n\n---\nThe researcher asks: {last['content']}"
        messages[-1] = {**last, "content": question}
    papers: list[Paper] = []
    said: list[str] = []
    searches = reads = proposed = 0
    while True:
        tools = [SEARCH_TOOL] if searches < max_searches else []
        if view is not None and reads < max_reads:
            tools.append(READ_TOOL)
        if view is not None and proposed < MAX_PROPOSALS:
            tools.append(PROPOSE_TOOL)
        calls = []
        for piece in provider.stream(messages, tools or None):
            if isinstance(piece, ToolCall):
                calls.append(piece)
            else:
                said.append(piece)
                yield {"type": "text", "text": piece}
        # Done when the model answered, or asked only for tools it was no longer offered
        offered = {t["function"]["name"] for t in tools}
        if not calls or not any(c.name in offered for c in calls):
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
            if call.name == "propose_analysis" and view is not None and proposed < MAX_PROPOSALS:
                proposed += 1
                areas = list(dict.fromkeys(s.area for s in view.series))
                try:
                    found = proposal(call.arguments, areas)
                except ProposalError as exc:
                    messages.append({"role": "tool", "content": f"Not proposed: {exc}."})
                    continue
                yield {"type": "proposal", "proposal": {**found, "title": describe_proposal(found)}}
                messages.append(
                    {
                        "role": "tool",
                        "content": (
                            f"Proposed: {describe_proposal(found)}. The researcher sees a button to "
                            "add it; nothing has run. Say in one sentence what it will show."
                        ),
                    }
                )
                continue
            if call.name == "read_series" and view is not None and reads < max_reads:
                reads += 1
                area = str(call.arguments.get("area", ""))
                variable = str(call.arguments.get("variable", ""))
                year = call.arguments.get("year")
                year = int(year) if str(year or "").isdigit() else None
                yield {"type": "read", "area": area, "variable": variable, "year": year}
                reading = view.read(area, variable, year)
                sources.append(
                    (f"reading {area} {variable.upper()} {year or 'every year'}", reading)
                )
                messages.append({"role": "tool", "content": reading})
                continue
            searches += 1
            query = str(call.arguments.get("query", "")).strip()
            if call.name != "search_papers" or not query or searches > max_searches:
                messages.append(
                    {"role": "tool", "content": "Unknown tool, empty query or no more calls."}
                )
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
            sources += [
                (
                    f"paper [{first + i}]",
                    f"{p.short}. {p.title}. {p.venue or ''}. {p.abstract or ''}",
                )
                for i, p in enumerate(found)
            ]
            yield {
                "type": "papers",
                "papers": [{"n": first + i, **p.to_dict()} for i, p in enumerate(found)],
            }
            messages.append({"role": "tool", "content": for_the_model(found, first)})

    verdict = check("".join(said), papers)
    event = {"type": "check", "text": verdict.text, **verdict.to_dict()}
    # numbers are checked when there was something to check them against
    if view is not None or papers:
        event["numbers"] = [n.to_dict() for n in check_numbers(verdict.text, sources)]
    yield event
