"""The Magonia assistant: its rules, the language models it can talk through, and its tools."""

import json
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from engine.awareness import earlier_papers, files_asked_about, restated, wants_literature
from engine.awareness import listing as library_listing
from engine.catalogue import CATALOGUE
from engine.citations import check
from engine.facts import View
from engine.library import Library, Uploads
from engine.library import for_the_model as passages_for_the_model
from engine.literature import LiteratureError, Paper, find_papers
from engine.models import LABELS, SETTABLE
from engine.numbers import check_numbers
from engine.proposals import PROPOSE_TOOL, ProposalError, proposal
from engine.proposals import describe as describe_proposal
from engine.rank import ollama_embedder
from engine.route import SOURCES, glossary, route
from engine.standing import standing_instruction
from engine.support import Judge, check_support, faithfulness, judge_with

NAME = "Mago"  # the assistant; Magonia is the whole platform

SETTINGS = "; ".join(
    f"{LABELS[name]}: {', '.join(f'{k} ({low:g} to {high:g})' for k, (low, high) in keys.items())}"
    for name, keys in SETTABLE.items()
)

CORE = f"""You are {NAME}, the research assistant inside the Magonia platform, which researchers \
use to study vegetation, land surface temperature and drought from satellite data.

- Help only with agricultural and environmental remote sensing, and the statistics and \
methods around it. Politely decline anything else.
- Never invent a reference, a number or a result. If you do not know, say so.
- Say how sure you are, and say when evidence is thin or studies disagree.
- Be concise and plain. Researchers are busy.
- Questions on methods, such as models, their settings or statistics, may be answered from \
general knowledge: say it is general advice, and relate it to what Magonia lets them set."""

LITERATURE = """The literature:
- When a question is about what research has found, call search_papers first, with short \
English keywords. You may search again with different keywords if the first results miss.
- Base what you say about research only on the papers the search returns, and cite them by \
their number in square brackets, like [1] or [2, 4]. Cite nothing else, and never cite \
papers from memory.
- When passages from a paper's full text are given, prefer them to its abstract, and cite \
the page they come from, like [1, p. 6].
- Say what each study found and in what setting (place, crop, rainfed or irrigated, \
sensor, period), grouping studies whose settings are alike. Do not count studies for and \
against, and do not give an overall verdict: the researcher weighs the evidence.
- If the papers found do not answer the question, say so plainly instead of filling the gap."""

ABOUT = """Facts about yourself (state only these; do not guess beyond them):
- Magonia was built by Ilyes Khayati as an engineering capstone project.
- This conversation is saved in the researcher's current workspace and continues when they \
come back. Earlier messages in it are shown to you.
- You can search the literature through OpenAlex, and read the full text of open-access \
papers; of the others you see only the title and abstract. The researcher can add their own \
PDFs on the Library page. You are told which files are in their library; when a question is \
about one of them, or speaks to one, its passages are given to you.
- You can see the areas, variables and analyses open in Magonia, as facts computed by code, \
when the researcher has some open. You cannot see the map or the charts as pictures, and \
you cannot run new analyses yet."""

MODEL_SETTINGS = f"""- On the Model page the researcher chooses the models (Ridge, Random Forest, XGBoost), the \
lags, the test years, the calendar and the rolling evaluation. A model given no settings is \
tuned automatically on the training years; one given settings uses those, and the library's \
defaults for the rest. The settings they can give: {SETTINGS}."""

# Everything, for a general question; each kind of question gets only what it needs
RULES = f"{CORE}\n\n{LITERATURE}\n\n{ABOUT}\n{MODEL_SETTINGS}"
RULES_FOR = {
    "chat": f"{CORE}\n\n{ABOUT}",
    "research": f"{CORE}\n\n{LITERATURE}\n\n{ABOUT}",
    "method": f"{CORE}\n\n{ABOUT}\n{MODEL_SETTINGS}",
    "data": f"{CORE}\n\n{ABOUT}\n{MODEL_SETTINGS}",
    "general": RULES,
}
# Earlier messages sent with a question: enough to follow the thread, too few for a small
# model to copy its own earlier answers
HISTORY = 6
MAX_INSTRUCTIONS = 2000  # characters of the researcher's instructions given to the model

# Sent with the facts only, so that questions asked without a workspace are not steered by them
MAX_PROPOSALS = 2

# The researcher chooses what runs: proposing is offered only when the message asks for
# something to be run, and never when it says not to
RUN = re.compile(
    r"\b(run|add|propose|compute|calculate|start|set up|build|fit|train)\b"
    r"|\b(can you|could you|would you|please|let'?s|i'?d like( you)? to|i want( you)? to)\b"
    r".{0,20}\b(forecast|predict|decompose|split|separate|break (it |them )?down|detrend|"
    r"deseasonali[sz]e|correlate|do an?)\b"
    r"|^\s*(forecast|predict|decompose|split|separate|break down|detrend|deseasonali[sz]e|"
    r"correlate)\b",
    re.IGNORECASE,
)
NOT_RUN = re.compile(
    r"\b(don'?t|do not|no|never|stop|without|not)\b.{0,25}"
    r"\b(propos\w*|run\w*|add\w*|analys[ie]s|suggest\w*|work)\b"
    r"|\bjust (chat|talk|brainstorm)",
    re.IGNORECASE,
)


def asks_to_run(text: str) -> bool:
    return bool(RUN.search(text)) and not NOT_RUN.search(text)


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
- You cannot run analyses yourself. If an analysis the question needs is not open, say \
so and which one would answer it; never say an analysis was run or added.
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
                "variable": {"type": "string", "description": ", ".join(CATALOGUE)},
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


SYSTEM = {"role": "system", "content": RULES}


class Ollama:
    """A model served by Ollama, on this computer or another one on the network."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.url = url.rstrip("/")
        self.model = model
        self.name = f"{model} (Ollama)"
        # ranks papers by meaning; without the model on the server, ranking uses shared words
        self.embed = ollama_embedder(self.url, os.environ.get("MAGONIA_EMBED", "nomic-embed-text"))

    def stream(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Iterator[str | ToolCall]:
        body = {
            "model": self.model,
            # the rules for this kind of question, when answer() chose them
            "messages": [
                *([] if messages and messages[0]["role"] == "system" else [SYSTEM]),
                *messages,
            ],
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
    library: Library | None = None,
    judge: Judge | None = None,
    instructions: str = "",
) -> Iterator[dict]:
    """Answer the last message of the conversation, using tools when the model asks.

    With a view, the facts about the researcher's open workspace go with the question and the
    model may read their series more closely. Yields events for the interface: what was read,
    text pieces, searches, the papers found, and at the end the check, whose text replaces the
    streamed answer: citations checked against the papers found and, when there was a
    workspace or papers, every number checked against what the model was given.
    """
    text = str(conversation[-1]["content"])
    if search is None:
        embed = getattr(provider, "embed", None)

        def search(query: str) -> list[Paper]:
            return find_papers(query, text, embed=embed)

    areas = list(dict.fromkeys(s.area for s in view.series)) if view is not None else []
    kind = route(text, areas, view is not None)
    if view is not None and view.focus and kind != "research":
        kind = "data"  # asked from a card: about what the card shows
    # the researcher's own files: listed for every question, read when one is about them
    files = Uploads(library).all() if library is not None else []
    own = files_asked_about(text, files)
    if own and kind == "chat":
        kind = "research"  # a question about their paper is not small talk
    # the papers earlier answers cited, which the model may cite again by new numbers
    earlier = earlier_papers(conversation[-HISTORY - 1 : -1])
    conversation = restated(conversation)
    yield {"type": "route", "kind": kind, "source": SOURCES[kind]}
    facts = view is not None and kind in ("data", "general")
    messages = [
        {"role": "system", "content": RULES_FOR[kind]},
        *conversation[-HISTORY - 1 :],
    ]
    # what the model is given, against which every number in its answer is checked
    sources = [("your question", text)]
    if kind in ("method", "data", "general"):
        sources.append(("the Model page's settings", MODEL_SETTINGS))
    if facts:
        sources += [(fact.card, fact.text) for fact in view.facts()]
        sources += [("your workspace", line) for line in view.context]
        yield {"type": "view", "cards": view.cards()}
        last = messages[-1]
        # the question comes last, where a small model attends to it best
        question = f"{view.sheet()}\n\n{DATA_RULES}\n\n---\nThe researcher asks: {last['content']}"
        messages[-1] = {**last, "content": question}
    elif kind == "method" and (known := glossary(text)):
        sources.append(("Magonia's catalogue", known))
        messages[-1] = {**messages[-1], "content": f"{known}\n\n---\nThe researcher asks: {text}"}
    papers: list[Paper] = []
    pages: dict[int, set[int]] = {}  # the pages of each paper whose passages the model read
    evidence: dict[int, list[tuple[str, str]]] = {}  # what the model was given from each paper
    if library is not None:
        messages[0]["content"] += f"\n\n{library_listing(files)}"
        sources.append(("your library", library_listing(files)))
    if earlier:
        papers.extend(earlier)
        for n, p in enumerate(earlier, start=1):
            evidence[n] = [(f"[{n}] abstract", f"{p.title}. {p.abstract or ''}")]
            sources.append(
                (f"paper [{n}]", f"{p.short}. {p.title}. {p.venue or ''}. {p.abstract or ''}")
            )
        yield {
            "type": "papers",
            "papers": [{"n": n, **p.to_dict()} for n, p in enumerate(earlier, 1)],
        }
        messages[0]["content"] += (
            "\n\nPapers cited earlier in this conversation. When you mention one of them again, "
            f"cite it by the number given here:\n{for_the_model(earlier, 1)}"
        )
    if judge is None and isinstance(provider, Ollama):
        judge = judge_with(provider.stream, (ProviderError, OSError))
    if instructions.strip():
        # the researcher's own instructions come after the rules, which still win
        messages[0]["content"] += (
            "\n\nThe researcher's instructions for you. Follow them unless they conflict with "
            f"the rules above:\n{instructions.strip()[:MAX_INSTRUCTIONS]}"
        )
    if library is not None and (own or kind in ("research", "general")):
        # the researcher's own files the question is about, or that speak to it, cited like
        # papers
        mine, chosen = (
            Uploads(library).asked_about(text, own, len(papers) + 1)
            if own
            else Uploads(library).relevant(text, len(papers) + 1)
        )
        if mine:
            papers.extend(mine)
            yield {
                "type": "papers",
                "papers": [
                    {"n": len(papers) - len(mine) + 1 + i, **p.to_dict()}
                    for i, p in enumerate(mine)
                ],
            }
            yield {
                "type": "passages",
                "read": {f.n: "read" for f in chosen},
                "passages": [f.to_dict() for f in chosen],
            }
            for f in chosen:
                pages.setdefault(f.n, set()).add(f.page)
                evidence.setdefault(f.n, []).append((f"[{f.n}, p. {f.page}]", f.text))
            sources += [(f"your file [{f.n}] p. {f.page}", f.text) for f in chosen]
            listing = "\n".join(
                f"[{len(papers) - len(mine) + 1 + i}] {p.title}" for i, p in enumerate(mine)
            )
            if own:
                # asked about their file: its text goes right before the question, where a
                # small model reads it, or it asks for the text it was given (measured, u01)
                last = messages[-1]
                messages[-1] = {
                    **last,
                    "content": "The researcher's own files this question is about, with "
                    f"passages from them. Answer from these passages and cite them by their "
                    f"number:\n{listing}\n\n{passages_for_the_model(chosen)}\n\n---\n"
                    f"The researcher asks: {last['content']}",
                }
            else:
                messages[0]["content"] += (
                    "\n\nThe researcher's own files that speak to this question. Cite them "
                    f"like papers, by their number:\n{listing}\n\n{passages_for_the_model(chosen)}"
                )
    if wanted := standing_instruction(text):
        # proposed in their own words; saved only if they click (AI-07)
        yield {
            "type": "proposal",
            "proposal": {
                "kind": "instruction",
                "label": "instruction",
                "title": wanted,
                "why": "Kept for every question in this workspace; edit it on the Library page.",
                "text": wanted,
            },
        }
        messages[-1] = {
            **messages[-1],
            "content": f"{messages[-1]['content']}\n\n(Note from Magonia: the researcher wants "
            f'"{wanted}" kept as a standing instruction. Under your answer they see a button to '
            "save it; it is not saved until they click it. Say so in one short sentence, and "
            "follow it in this answer.)",
        }
    said: list[str] = []
    searches = reads = proposed = refused = 0
    if own and not wants_literature(text):
        searches = max_searches  # a question about their own file needs no search
    if not asks_to_run(text):
        proposed = MAX_PROPOSALS
    while True:
        tools = [SEARCH_TOOL] if searches < max_searches and kind in ("research", "general") else []
        if facts and reads < max_reads:
            tools.append(READ_TOOL)
        if facts and proposed < MAX_PROPOSALS:
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
            if call.name == "propose_analysis" and facts and proposed < MAX_PROPOSALS:
                areas = list(dict.fromkeys(s.area for s in view.series))
                try:
                    found = proposal(call.arguments, areas)
                except ProposalError as exc:
                    # a refused proposal does not use up a try, so the model can correct it
                    messages.append(
                        {
                            "role": "tool",
                            "content": f"Not proposed: {exc}. Correct it and call again.",
                        }
                    )
                    refused += 1
                    if refused >= MAX_PROPOSALS:
                        proposed = MAX_PROPOSALS  # it keeps getting it wrong: stop offering
                    continue
                proposed += 1
                yield {"type": "proposal", "proposal": {**found, "title": describe_proposal(found)}}
                messages.append(
                    {
                        "role": "tool",
                        "content": (
                            f"Proposed: {describe_proposal(found)}. The researcher sees a button to "
                            "add it; nothing has run. Now answer their question; mention the "
                            "proposal in one sentence at most."
                        ),
                    }
                )
                continue
            if call.name == "read_series" and facts and reads < max_reads:
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
            for i, p in enumerate(found):
                evidence[first + i] = [
                    (f"[{first + i}] abstract", f"{p.title}. {p.abstract or ''}")
                ]
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
            given = for_the_model(found, first)
            if library is not None and any(p.pdf_url for p in found):
                # the full text of the open-access papers, and its passages that answer
                yield {"type": "reading", "count": sum(1 for p in found if p.pdf_url)}
                status = library.add_all(found)
                numbered = {first + i: p for i, p in enumerate(found)}
                chosen = library.best(text, numbered)
                for f in chosen:
                    pages.setdefault(f.n, set()).add(f.page)
                    evidence[f.n].append((f"[{f.n}, p. {f.page}]", f.text))
                sources += [(f"paper [{f.n}] p. {f.page}", f.text) for f in chosen]
                yield {
                    "type": "passages",
                    "read": {n: status[p.id] for n, p in numbered.items()},
                    "passages": [f.to_dict() for f in chosen],
                }
                if chosen:
                    given += "\n\n" + passages_for_the_model(chosen)
            messages.append({"role": "tool", "content": given})

    verdict = check("".join(said), papers, pages)
    event = {"type": "check", "text": verdict.text, **verdict.to_dict()}
    # numbers are checked when there was something to check them against
    if facts or papers or kind == "method":
        event["numbers"] = [n.to_dict() for n in check_numbers(verdict.text, sources)]
    if verdict.cited:
        # does each cited statement say what its papers say?
        yield {"type": "verifying"}
        embed = getattr(provider, "embed", None)
        found = check_support(verdict.text, evidence, embed=embed, judge=judge)
        event["support"] = [s.to_dict() for s in found]
        event["faithfulness"] = faithfulness(found)
    yield event
