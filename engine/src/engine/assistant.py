"""The Magonia assistant: its rules, the language models it can talk through, and its tools."""

import json
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from engine import claims, honesty, interface
from engine.awareness import earlier_papers, files_asked_about, restated, wants_literature
from engine.awareness import listing as library_listing
from engine.board import Pinned
from engine.board import block as board_block
from engine.board import check as board_check
from engine.board import given as board_items
from engine.catalogue import CATALOGUE
from engine.citations import check
from engine.facts import View
from engine.library import Library, Uploads
from engine.library import for_the_model as passages_for_the_model
from engine.literature import LiteratureError, Paper, find_papers, keywords
from engine.models import LABELS, SETTABLE
from engine.numbers import check_numbers
from engine.proposals import PROPOSE_TOOL, ProposalError, proposal
from engine.proposals import WORDS as VARIABLE_WORDS
from engine.proposals import describe as describe_proposal
from engine.proposals import named as named_variables
from engine.rank import ollama_embedder
from engine.route import GREETING, SOURCES, follows, glossary, in_french, route, together
from engine.standing import standing_instruction
from engine.support import (
    CANDIDATES,
    Judge,
    check_support,
    check_uncited,
    faithfulness,
    judge_with,
    withdraw,
)

NAME = "Magon"  # the assistant; Magonia is the whole platform

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
- Answer in the language the researcher writes in, even when the papers are in English.
- Never name your tools or write code for them: say in words what you looked at.
- Write formulas in plain text, like NDVI = (NIR − Red) / (NIR + Red), never in LaTeX.
- End when the answer is complete, without offering more help.
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
you cannot run analyses yourself: you can propose one, which the researcher adds with a click."""

# What the interface really has, so that Magon points to it instead of inventing buttons
APP = interface.described()

MODEL_SETTINGS = f"""- On the Model page the researcher chooses the models (Ridge, Random Forest, XGBoost), the \
lags, the test years, the calendar and the rolling evaluation. A model given no settings is \
tuned automatically on the training years; one given settings uses those, and the library's \
defaults for the rest. The settings they can give: {SETTINGS}."""

# Everything, for a general question; each kind of question gets only what it needs
RULES = f"{CORE}\n\n{LITERATURE}\n\n{ABOUT}\n{MODEL_SETTINGS}\n\n{APP}"
RULES_FOR = {
    "chat": f"{CORE}\n\n{ABOUT}\n\n{APP}",
    "research": f"{CORE}\n\n{LITERATURE}\n\n{ABOUT}",
    "method": f"{CORE}\n\n{ABOUT}\n{MODEL_SETTINGS}\n\n{APP}",
    "data": f"{CORE}\n\n{ABOUT}\n{MODEL_SETTINGS}\n\n{APP}",
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
    r"correlate)\b"
    # "let's start with seasonal patterns", "yes, go with the trend", "give me buttons"
    r"|\b(let'?s|start with|go with|begin with|proceed|go ahead|i'?d like|i want|yes)\b"
    r".{0,40}\b(season\w*|trends?|correlat\w*|lags?|memory|phenolog\w*|analys[ie]s|"
    r"coherence|experiments?|forecasts?|decompos\w*)\b"
    r"|\bbuttons?\b",
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


# The words that open a reply without saying anything: "ok", "great, so", "cool and"
FILLER = re.compile(
    r"^\s*((ok(ay)?|great|cool|right|alright|so|and|then|well)[\s,.!]*)+", re.IGNORECASE
)

# A year the question names, from 1950 to 2099
ASKED_YEAR = re.compile(r"(?<![\w.])(19[5-9]\d|20\d\d)(?![\w.%])")
MAX_ASKED_READINGS = 3


def asked_readings(question: str, view: View) -> list[tuple[str, str, int]]:
    """The series a question asks about for a given year: (area, variable, year).

    A question naming a year and a variable open in the workspace ("the monthly NDVI values
    in 2023") is about that year's values, which the facts do not hold. The area is the one
    named, or every open one when none is.
    """
    years = list(dict.fromkeys(int(y) for y in ASKED_YEAR.findall(question)))
    if not years:
        return []
    lower = question.lower()
    variables = [
        key
        for key in dict.fromkeys(s.key for s in view.series)
        if any(w in lower for w in VARIABLE_WORDS.get(key, (key,)))
    ]
    areas = list(dict.fromkeys(s.area for s in view.series))
    named = [a for a in areas if a and a.lower() in lower] or areas
    wanted = [(a, v, y) for y in years for v in variables for a in named]
    return wanted[:MAX_ASKED_READINGS]


def english_keywords(provider: "Provider", question: str, query: str) -> str:
    """Search keywords in English for a question asked in another language.

    Asked of the model in one short call when it can be asked; otherwise the query stays as
    it was written.
    """
    ask = getattr(provider, "english_keywords", None)
    if ask is None:
        return query
    try:
        return ask(question) or query
    except (ProviderError, OSError):
        return query


# An analysis named in a request, in the words a question or a model uses, most specific first
ANALYSIS_WORDS = [
    (
        re.compile(
            r"decompos|trend and season|seasonal part|break (it |them )?down", re.IGNORECASE
        ),
        "decomposition",
    ),
    (re.compile(r"\blags?\b|memory|lagged", re.IGNORECASE), "lags"),
    (re.compile(r"season dates|phenolog|green-?up|senescence", re.IGNORECASE), "phenology"),
    (re.compile(r"forecast|predict|experiment", re.IGNORECASE), "experiment"),
    (re.compile(r"correlat", re.IGNORECASE), "correlation"),
    (re.compile(r"\btrends?\b|mann-?kendall", re.IGNORECASE), "trend"),
]
# The words a model writes when it describes a proposal instead of making it
PROSE_PROPOSAL = re.compile(
    r"^[ \t]*[*_]*(proposed action|proposal|suggested action)[*_]*\s*:.*(\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def proposal_in_words(question: str, answer: str, areas: list[str]) -> dict | None:
    """The analysis a request asks for, when the model described it instead of proposing it.

    Read from the question first and then from the answer's own description; checked by the
    same validator as a proposal the model makes. None when nothing valid can be proposed.
    """
    described = " ".join(m.group(0) for m in PROSE_PROPOSAL.finditer(answer))
    for text in (question, described):
        for pattern, kind in ANALYSIS_WORDS:
            if pattern.search(text):
                arguments = {"kind": kind}
                if asked := named_variables(question):
                    arguments["variable"] = asked[0]
                    if kind == "correlation" and len(asked) > 1:
                        arguments["driver"] = asked[1]
                try:
                    return proposal(arguments, areas, question)
                except ProposalError:
                    return None
    return None


DATA_RULES = """How to use these facts:
- If the question is about the researcher's areas or results, answer from the facts. Copy \
numbers exactly as written, never compute new ones, and name the chart or analysis each \
number comes from, for example "(NDVI chart)".
- The facts do not contain the values of single months or years. When asked for them, call \
read_series (one area and variable, a year or every year) and quote what it returns. Never \
write a value you were not given.
- A question about a year (which year was lowest, driest, greenest) is answered with the \
annual means: quote the "annual means" fact, never a single month.
- A question about when in the year, or how high or low it usually goes, is answered with \
the average year: quote both ends from the "average year" fact, never a single month.
- Higher SPEI means wetter, lower (negative) SPEI drier. Higher LST means a hotter surface.
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


TOOLS = {"search_papers", "read_series", "propose_analysis"}


# What a small model adds that the researcher should never read: its tools named in a sentence
# or a code block, and a closing offer of more help
TOOL_NAMED = re.compile(r"`?\b(read_series|search_papers)\b`?")
CODE = re.compile(r"```[a-z]*\n.*?```", re.DOTALL)
CLOSING = re.compile(
    r"\n+\s*(if you have any|feel free to|let me know if|i hope this helps|do you want me to|"
    r"would you like me to)[^\n]*\s*$",
    re.IGNORECASE,
)


def tidy(text: str) -> str:
    """The answer without the machinery: code blocks and sentences that name a tool, and a
    closing offer of more help."""
    text = CODE.sub(lambda m: "" if TOOL_NAMED.search(m.group()) else m.group(), text)
    lines = []
    for line in text.split("\n"):
        if TOOL_NAMED.search(line):
            # keep the line's bullet and label, and those of its sentences that name no tool
            head = re.match(r"\s*(?:[-*•]|\d+\.)?\s*(?:\*\*[^*]+\*\*\s*)?", line).group()
            kept = [
                s for s in re.split(r"(?<=[.!?])\s+", line[len(head) :]) if not TOOL_NAMED.search(s)
            ]
            if not kept:
                continue
            line = head + " ".join(kept)
        lines.append(line)
    text = "\n".join(lines)
    while (closing := CLOSING.search(text)) and closing.start() > 0:
        text = text[: closing.start()]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# A search written as a function call in the text: 'Search_papers("olive NDVI hail")' (14 Nov)
SEARCH_IN_WORDS = re.compile(
    r"`?\bsearch_papers\s*\(\s*(?:query\s*=\s*)?[\"'“”‘’]([^\"'“”‘’)]{2,200})[\"'“”‘’]\s*\)`?",
    re.IGNORECASE,
)


def written_calls(text: str) -> tuple[list[ToolCall], str]:
    """Tool calls the model wrote into its answer instead of making them.

    A small model sometimes does, as JSON or as a function call in a sentence; the
    researcher would see it, and a search written out is a search that never ran. Returns
    the calls and the text without them.
    """
    found_in_words = [
        ToolCall("search_papers", {"query": m.group(1).strip()})
        for m in SEARCH_IN_WORDS.finditer(text)
    ]
    if found_in_words:
        return found_in_words, SEARCH_IN_WORDS.sub("", text).strip()
    decoder = json.JSONDecoder()
    calls, kept, at = [], [], 0
    for start in re.finditer(r"(```(?:json)?\s*)?\{", text):
        if start.start() < at:
            continue
        try:
            found, end = decoder.raw_decode(text, start.end() - 1)
        except ValueError:
            continue
        if not (isinstance(found, dict) and found.get("name") in TOOLS):
            continue
        arguments = found.get("arguments") or found.get("parameters") or {}
        if not isinstance(arguments, dict):
            continue
        if start.group(1) and (fence := re.match(r"\s*```", text[end:])):
            end += fence.end()
        calls.append(ToolCall(found["name"], arguments))
        kept.append(text[at : start.start()])
        at = end
    if not calls:
        return [], text
    kept.append(text[at:])
    return calls, re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()


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
# How long Ollama keeps the model loaded after a question; "-1" keeps it until it restarts
KEEP_ALIVE = os.environ.get("MAGONIA_KEEP_ALIVE", "60m")


class Ollama:
    """A model served by Ollama, on this computer or another one on the network."""

    def __init__(
        self,
        url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        temperature: float | None = None,  # None keeps the model's own
    ):
        self.url = url.rstrip("/")
        self.model = model
        self.temperature = temperature
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
            # the model stays loaded between questions: Ollama unloads it after 5 idle
            # minutes, and the next question waits for it to load again (a "Hi" took 13 s)
            "keep_alive": KEEP_ALIVE,
            "options": {
                "num_ctx": 8192,  # room for the abstracts of the papers found
                **({} if self.temperature is None else {"temperature": self.temperature}),
            },
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
                "Magon is not available right now: its language model is not answering. "
                "Try again in a minute."
            ) from exc
        # Ollama sends one JSON object per line, each with the next piece of the answer
        with response:
            for line in response:
                piece = json.loads(line)
                if "error" in piece:
                    raise ProviderError(
                        "Magon stopped before finishing its answer. Ask again in a moment."
                    )
                message = piece.get("message", {})
                for call in message.get("tool_calls") or []:
                    yield ToolCall(
                        call["function"]["name"], call["function"].get("arguments") or {}
                    )
                if text := message.get("content"):
                    yield text

    def english_keywords(self, question: str) -> str:
        """Short English search keywords for a question in another language."""
        asked = [
            {
                "role": "system",
                "content": "You translate research questions into English search keywords.",
            },
            {
                "role": "user",
                "content": "Give 3 to 6 English search keywords for this question, separated by "
                f"spaces, and nothing else.\n\nQuestion: {question}",
            },
        ]
        said = "".join(p for p in self.stream(asked) if isinstance(p, str))
        return " ".join(re.findall(r"[A-Za-z0-9-]+", said)[:8])


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


def from_environment(settings: dict | None = None) -> Provider:
    """The provider named by MAGONIA_MODEL_URL and MAGONIA_MODEL, in the environment or .env,
    unless the researcher chose another server or model in Magonia's settings."""
    load_dotenv()
    settings = settings or {}
    url = settings.get("model_url") or os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434")
    if url == "scripted":
        return Scripted()
    model = settings.get("model") or os.environ.get("MAGONIA_MODEL", "qwen2.5:7b")
    return Ollama(url, model, settings.get("temperature"))


def installed_models(url: str) -> list[str]:
    """The chat models on an Ollama server; embedding models cannot answer, so are left out."""
    with urlopen(f"{url.rstrip('/')}/api/tags", timeout=5) as response:
        names = [m["name"] for m in json.load(response).get("models", [])]
    return sorted(n for n in names if "embed" not in n)


# How long Magon's answers are, as the researcher chose in its settings
CONCISE = "- Be concise and plain. Researchers are busy."
DETAILED = (
    "- Be plain and thorough: give the reasoning, the setting of each finding and its limits."
)


def for_the_model(papers: list[Paper], first: int) -> str:
    """Numbered papers as the model reads them; abstracts are shortened to save context."""
    if not papers:
        return "No papers were found. Try other keywords, or say that nothing was found."
    lines = ["Papers found. Cite them by number, e.g. [1]."]
    for n, paper in enumerate(papers, start=first):
        summary = (paper.abstract or "No abstract available.")[:700]
        lines.append(f"[{n}] {paper.short}. {paper.title}. {paper.venue or ''}\n{summary}")
    return "\n\n".join(lines)


class Clock:
    """Seconds spent in each stage of an answer, so the time of a slow one can be read."""

    def __init__(self):
        self.started = time.monotonic()
        self.spent: dict[str, float] = defaultdict(float)

    def add(self, stage: str, since: float) -> None:
        self.spent[stage] += time.monotonic() - since

    def report(self) -> dict[str, float]:
        out = {stage: round(s, 2) for stage, s in self.spent.items()}
        out["total"] = round(time.monotonic() - self.started, 2)
        return out


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
    papers_per_search: int = 6,
    detail: str = "concise",
    search_mode: str = "keyword",
    withdraw_unsupported: bool = True,
    board: list[Pinned] | None = None,
) -> Iterator[dict]:
    """Answer the last message of the conversation, using tools when the model asks.

    With a view, the facts about the researcher's open workspace go with the question and the
    model may read their series more closely. Yields events for the interface: what was read,
    text pieces, searches, the papers found, and at the end the check, whose text replaces the
    streamed answer: citations checked against the papers found and, when there was a
    workspace or papers, every number checked against what the model was given.
    """
    clock = Clock()
    text = str(conversation[-1]["content"])
    topic = text  # what the papers are ranked against; a follow-up adds the earlier question
    if search is None:
        embed = getattr(provider, "embed", None)

        def search(query: str) -> list[Paper]:
            if search_mode == "hybrid":
                return find_papers(query, topic, keep=papers_per_search, embed=embed, hybrid=True)
            return find_papers(query, topic, keep=papers_per_search, embed=embed)

    areas = list(dict.fromkeys(s.area for s in view.series)) if view is not None else []
    kind = route(text, areas, view is not None)
    # a short follow-up ("And in Tunisia?") asks the earlier question again about something else
    earlier_question = next(
        (str(m["content"]) for m in reversed(conversation[:-1]) if m.get("role") == "user"), ""
    )
    follow_up = bool(earlier_question) and follows(text) and kind in ("general", "method")
    if follow_up and route(earlier_question, areas, view is not None) == "research":
        kind = "research"
    # a reply that only carries the conversation on ("ok I added it") is about what the
    # question before was about, and gets the same facts and tools: routed as small talk, it
    # got none and Magon invented the result it was told to read (14 Nov). But "ok" before a
    # question of its own ("ok what lag is important for ndvi here?") starts a new one, which
    # is routed on its own words: inheriting sent a data question to the literature (14 Nov)
    if kind == "chat" and earlier_question and not GREETING.match(text):
        rest = FILLER.sub("", text)
        if rest.rstrip().endswith("?") or len(rest.split()) >= 5:
            kind = route(rest, areas, view is not None)
        else:
            kind = route(earlier_question, areas, view is not None)
    if view is not None and view.focus and kind != "research":
        kind = "data"  # asked from a card: about what the card shows
    # a claim to test on the researcher's data is a question about their data (#171)
    testing = view is not None and claims.asks_to_test(text)
    if testing:
        kind = "data"
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
    rules = RULES_FOR[kind] if detail != "detailed" else RULES_FOR[kind].replace(CONCISE, DETAILED)
    messages = [
        {"role": "system", "content": rules},
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
    # the values of a year the question names are read by code before the model answers:
    # left to the model, it skipped the tool and wrote twelve months of its own (14 Nov)
    readings = asked_readings(text, view) if facts else []
    for area, variable, year in readings:
        yield {"type": "read", "area": area, "variable": variable, "year": year}
        reading = view.read(area, variable, year)
        sources.append((f"reading {area} {variable.upper()} {year}", reading))
        messages[-1] = {
            **messages[-1],
            "content": f"Read from the researcher's series: {reading}\n\n{messages[-1]['content']}",
        }
    # a claim tested by code on the researcher's data; the model reports the verdict, it does
    # not reach one (#171)
    if testing:
        claim = claims.read(claims.claim_in(text))
        if claim is None:
            result = None
            note = (
                "Magonia could not read a claim it can test in this message: it tests a "
                "driver acting on vegetation (with or without a delay) and a long-term trend. "
                "Say so, and ask for the claim in one sentence."
            )
        else:
            result = claims.test(claim, view)
            yield {"type": "claim_test", "test": result.to_dict()}
            sources += [("the claim test", line) for line in result.summary]
            note = claims.block(result)
        messages[-1] = {**messages[-1], "content": f"{note}\n\n{messages[-1]['content']}"}
    # what a variable means, for a question that mixes kinds: the sign of SPEI was turned
    # upside down when no definition was given (14 Nov)
    if kind == "general" and (meaning := glossary(text)):
        sources.append(("Magonia's catalogue", meaning))
        messages[-1] = {**messages[-1], "content": f"{meaning}\n\n{messages[-1]['content']}"}
    elif kind == "method" and (known := glossary(text)):
        sources.append(("Magonia's catalogue", known))
        messages[-1] = {**messages[-1], "content": f"{known}\n\n---\nThe researcher asks: {text}"}
    # what the researcher pinned, as evidence it can cite [B1]…; not for small talk
    shown = board_items(board or [], text) if kind != "chat" else []
    if shown:
        yield {"type": "board", "items": [b.to_dict() for b in shown]}
        sources += [(f"your board [B{b.n}]", b.text) for b in shown]
        messages[-1] = {
            **messages[-1],
            "content": f"{board_block(shown)}\n\n---\n{messages[-1]['content']}",
        }
    # a follow-up of a literature question is searched by code: given the earlier papers, the
    # model answered from them instead of searching again (measured, f01)
    forced: list[ToolCall] = []
    if follow_up and kind == "research":
        messages[-1] = {
            **messages[-1],
            "content": f'{text}\n\n(This follows the earlier question: "{earlier_question}". '
            "Answer it about what is asked now, from the papers of the new search.)",
        }
        topic = together(text, earlier_question)
        forced = [ToolCall("search_papers", {"query": keywords(topic)})]
    if in_french(text):
        # said last, where a small model attends to it, or it answers in the papers' English
        messages[-1] = {
            **messages[-1],
            "content": f"{messages[-1]['content']}\n\n(Réponds en français.)",
        }
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
    searches = proposed = refused = 0
    reads = len(readings)
    cards_proposed = 0
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
        begun = len(said)
        if forced and tools and tools[0] is SEARCH_TOOL:
            calls, forced = forced, []
        else:
            since = time.monotonic()
            for piece in provider.stream(messages, tools or None):
                if isinstance(piece, ToolCall):
                    calls.append(piece)
                else:
                    said.append(piece)
                    yield {"type": "text", "text": piece}
            clock.add("model", since)
        offered = {t["function"]["name"] for t in tools}
        if not calls:
            written, _ = written_calls("".join(said[begun:]))
            if any(c.name in offered for c in written):
                # it wrote the call out instead of making it: make it, and take back what
                # it said on the way, as it would have said nothing
                calls = written
                del said[begun:]
                yield {"type": "rewrite", "text": "".join(said)}
        if (
            not calls
            and kind == "research"
            and searches == 0
            and not own
            and not earlier
            and SEARCH_TOOL in tools
        ):
            # it answered a question about research without searching, from memory: that is
            # how a paper that does not exist got a summary (14 Nov). Code searches instead,
            # and the model answers again from what is found. Not when the question is about
            # the researcher's own files or the papers an earlier answer cited: those are
            # given. A library file that merely speaks to the question is no reason to skip
            # the search: with one given, the model attributed invented findings to it
            calls = [ToolCall("search_papers", {"query": keywords(topic)})]
            del said[begun:]
            yield {"type": "rewrite", "text": "".join(said)}
        # Done when the model answered, or asked only for tools it was no longer offered
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
                    found = proposal(call.arguments, areas, text)
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
                cards_proposed += 1
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
            if query and in_french(text):
                # OpenAlex is searched in English: a French query found nothing (14 Nov)
                query = english_keywords(provider, text, query)
            if call.name != "search_papers" or not query or searches > max_searches:
                messages.append(
                    {"role": "tool", "content": "Unknown tool, empty query or no more calls."}
                )
                continue
            yield {"type": "search", "query": query}
            since = time.monotonic()
            try:
                found = search(query)
            except LiteratureError as exc:
                clock.add("search", since)
                yield {"type": "search_failed", "query": query, "error": str(exc)}
                messages.append({"role": "tool", "content": f"The search failed: {exc}"})
                continue
            clock.add("search", since)
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
                since = time.monotonic()
                status = library.add_all(found)
                numbered = {first + i: p for i, p in enumerate(found)}
                chosen = library.best(text, numbered)
                clock.add("reading", since)
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

    _, said_text = written_calls("".join(said))  # a call it can no longer make is not shown
    wrote_one = PROSE_PROPOSAL.search(said_text)
    if facts and asks_to_run(text) and cards_proposed == 0 and refused == 0 and wrote_one:
        # it described the analysis in words ("Proposed action: Add analysis, Decomposition")
        # instead of proposing it, and the researcher got no button (14 Nov): code proposes
        # the one the question asks for, and the words go. Not when it tried the tool and was
        # refused: then the request did not fit the workspace (an area that is not open)
        found = proposal_in_words(text, said_text, list(dict.fromkeys(s.area for s in view.series)))
        if found is not None:
            yield {"type": "proposal", "proposal": {**found, "title": describe_proposal(found)}}
            said_text = PROSE_PROPOSAL.sub("", said_text)
    since = time.monotonic()
    verdict = check(tidy(said_text), papers, pages)
    clock.add("checks", since)
    final = verdict.text
    if shown:
        # a board item it was not given cannot be cited
        final, event_cited, event_removed = board_check(final, shown)
    event = {"type": "check", **verdict.to_dict()}
    if shown:
        event["board_cited"], event["board_removed"] = event_cited, event_removed
    # what it says against what Magon can check outright: a paper that was not found, a
    # search it did not make, a definition turned upside down. Withdrawn whatever the
    # setting for unsupported statements, because it is contradicted, not just unsupported
    contradicted = honesty.withdrawn(final, papers, searched=searches > 0)
    if contradicted:
        final, _, gone = withdraw(final, contradicted, note=honesty.note(len(contradicted)))
        event["withdrawn"] = [s.to_dict() for s in gone]
    embed = getattr(provider, "embed", None)

    def elsewhere(claim: str, cites: list[int]) -> list[tuple[str, str]]:
        # the passages closest to the claim in the whole text of the papers numbered, as
        # the library keeps it; a paper read only to its abstract has none
        if library is None:
            return []
        numbered = {n: papers[n - 1] for n in cites if 0 < n <= len(papers)}
        found = library.best(claim, numbered, keep=CANDIDATES, per_paper=CANDIDATES)
        return [(f"[{f.n}, p. {f.page}]", f.text) for f in found]

    if verdict.cited:
        # does each cited statement say what its papers say?
        yield {"type": "verifying"}
        since = time.monotonic()
        found = check_support(final, evidence, embed=embed, judge=judge, more=elsewhere)
        clock.add("support", since)
        event["faithfulness"] = faithfulness(found)  # of what the model wrote
        if withdraw_unsupported:
            # a statement its papers do not support leaves the answer, which says so
            final, found, gone = withdraw(final, found)
            event["withdrawn"] = event.get("withdrawn", []) + [s.to_dict() for s in gone]
        event["support"] = [s.to_dict() for s in found]
    if kind == "research" and papers:
        # the sentences that cite nothing: checked against every paper found, and marked,
        # so that not citing is not a way past the check
        since = time.monotonic()
        loose = check_uncited(final, evidence, embed=embed, judge=judge, more=elsewhere)
        clock.add("support", since)
        event["uncited"] = [s.to_dict() for s in loose]
    since = time.monotonic()
    event["text"] = final
    # numbers are checked when there was something to check them against
    if facts or papers or shown or kind == "method":
        event["numbers"] = [n.to_dict() for n in check_numbers(final, sources)]
    # every page, button or analysis it names must be one the interface has
    event["app"] = [m.to_dict() for m in interface.check_app(final)]
    clock.add("checks", since)
    # where the time went: the model, searching, reading papers, checking, judging support
    event["timings"] = clock.report()
    yield event
