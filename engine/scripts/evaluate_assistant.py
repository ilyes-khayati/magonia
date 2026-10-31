"""Run a fixed set of questions through the assistant and measure how it behaves.

Uses the model named in .env (MAGONIA_MODEL_URL, MAGONIA_MODEL) and live OpenAlex.

    uv run python scripts/evaluate_assistant.py [results.json]

For each question it records whether the model searched, how many papers it found and cited,
how many citations the check removed (invented numbers), author–year mentions it could not
verify, the numbers it wrote and whether each was found in what it was given, and how long
the answer took. Each question starts a new conversation. Questions are of four kinds:

- research: should be answered from a search, with citations
- chat: greetings and off-topic requests, which should not trigger a search
- trap: questions about papers that do not exist, which must not be "confirmed"
- data: questions about a fixed workspace, the reference Jendouba orchard replayed from
  recorded Earth Engine answers, to be answered from the facts and readings
- run: requests, on that workspace, to run an analysis, which should be proposed
- talk: questions on that workspace that must be answered, not met with a proposal (taken
  from a conversation where proposals drowned the questions)
"""

import json
import math
import sys
import time
from pathlib import Path

from engine.assistant import answer, from_environment
from engine.facts import Series, View
from engine.pipeline import Request
from engine.pipeline import run as extract

DATA = Path(__file__).parent.parent / "tests" / "data"

QUESTIONS = [
    ("research", "What is known about drought and olive NDVI in the Mediterranean?"),
    ("research", "How long does NDVI take to respond to drought, measured with SPEI?"),
    ("research", "Is SAVI better than NDVI in sparse olive orchards?"),
    ("research", "What are the limits of MODIS NDVI at 250 m for small fields?"),
    ("research", "Which machine-learning models are used to forecast NDVI?"),
    ("research", "Does supplemental irrigation reduce drought stress in olive trees?"),
    ("chat", "Hello, who are you?"),
    ("chat", "Write me a short poem about cats."),
    ("trap", "Summarise the 2019 paper by Khayati on olive NDVI in Gabès."),
    ("trap", "What did Smith and Jones (2023) find about SAVI in Tunisian olive groves?"),
    ("data", "When does NDVI peak in my orchard, and how low does it go?"),
    ("data", "Is there a trend in my orchard's NDVI?"),
    ("data", "What were the monthly NDVI values of my orchard in 2012?"),
    ("data", "Does drought, measured by SPEI-3, affect NDVI in my orchard, and with what lag?"),
    ("data", "Which year had the lowest NDVI in my orchard?"),
    ("run", "Can you run a trend test on my orchard's NDVI?"),
    ("run", "Add a season-dates analysis for my orchard's NDVI."),
    ("talk", "What hyperparameters should I try for Random Forest and XGBoost?"),
    ("talk", "no don't propose anything, just give me a list of hyperparameters"),
    ("talk", "Let's just chat: why might olive and forest respond differently to drought?"),
]


def jendouba_view() -> View:
    """The reference orchard as a researcher would have it open: monthly NDVI, LST and SPEI-3
    charted, and NDVI correlated with SPEI-3."""
    geometry = json.loads((DATA / "jendouba_orchard.geojson").read_text())["features"][0][
        "geometry"
    ]
    series = []
    for key, recorded, masking, scale, title, units in [
        ("ndvi", "ndvi", "date", None, "NDVI", ""),
        ("lst", "lst", "none", None, "LST", "°C"),
        ("spei", "spei_3", "none", 3, "SPEI-3", ""),
    ]:
        path = DATA / "recorded" / f"{recorded}.json"
        request = Request(key, geometry, "2000-03-01", "2025-01-01", masking, scale, "monthly", 2)
        table = extract(request, fetch=lambda *args, path=path: json.loads(path.read_text())).table
        points = [
            {
                "date": row.date.date().isoformat(),
                "value": None if math.isnan(row.value) else float(row.value),
                "masked": bool(row.masked),
                "filled": bool(row.filled),
            }
            for row in table.itertuples()
        ]
        series.append(Series("Orchard", key, title, units, points))
    context = [
        "The researcher is on the charts page.",
        "Areas: Orchard (0.64 km²).",
        "Period 2000-03 to 2024-12, monthly values, gaps of up to 2 filled.",
    ]
    correlation = {"id": 1, "kind": "correlation", "response": "ndvi", "driver": "spei"}
    return View(context, series, ["ndvi", "lst", "spei"], [correlation | {"deseasonalise": True}])


def run(kind: str, question: str, provider, view: View | None = None) -> dict:
    start = time.time()
    searches, papers, reads, proposals, final, kind_routed = [], [], [], [], {}, None
    for event in answer(provider, [{"role": "user", "content": question}], view=view):
        if event["type"] == "search":
            searches.append(event["query"])
        elif event["type"] == "read":
            reads.append(event)
        elif event["type"] == "route":
            kind_routed = event["kind"]
        elif event["type"] == "proposal":
            proposals.append(event["proposal"]["title"])
        elif event["type"] == "papers":
            papers.extend(event["papers"])
        elif event["type"] == "check":
            final = event
    return {
        "kind": kind,
        "question": question,
        "route": kind_routed,
        "searches": searches,
        "found": len(papers),
        "cited": final.get("cited", []),
        "removed": final.get("removed", []),
        "unverified": final.get("unverified", []),
        "reads": reads,
        "proposals": proposals,
        "numbers": final.get("numbers", []),
        "seconds": round(time.time() - start, 1),
        "answer": final.get("text", ""),
    }


def summary(results: list[dict]) -> dict:
    research = [r for r in results if r["kind"] == "research"]
    chat = [r for r in results if r["kind"] == "chat"]
    numbers = [n for r in results if r["kind"] == "data" for n in r["numbers"]]
    verified = sum(n["status"] == "verified" for n in numbers)
    return {
        "research questions that searched": f"{sum(bool(r['searches']) for r in research)}/{len(research)}",
        "research answers with at least one checked citation": (
            f"{sum(bool(r['cited']) for r in research)}/{len(research)}"
        ),
        "chat questions that searched (should be 0)": f"{sum(bool(r['searches']) for r in chat)}/{len(chat)}",
        "invented citation numbers removed": sum(len(r["removed"]) for r in results),
        "unverified author-year mentions": sum(len(r["unverified"]) for r in results),
        "numbers in data answers found in what the model was given": f"{verified}/{len(numbers)}",
        "data answers that read the series": (
            f"{sum(bool(r['reads']) for r in results if r['kind'] == 'data')}"
            f"/{sum(r['kind'] == 'data' for r in results)}"
        ),
        "run requests that got a proposal": (
            f"{sum(bool(r['proposals']) for r in results if r['kind'] == 'run')}"
            f"/{sum(r['kind'] == 'run' for r in results)}"
        ),
        "talk questions that got a proposal (should be 0)": (
            f"{sum(bool(r['proposals']) for r in results if r['kind'] == 'talk')}"
            f"/{sum(r['kind'] == 'talk' for r in results)}"
        ),
        "median seconds per answer": sorted(r["seconds"] for r in results)[len(results) // 2],
    }


if __name__ == "__main__":
    provider = from_environment()
    view = jendouba_view()
    results = []
    for kind, question in QUESTIONS:
        result = run(kind, question, provider, view if kind in ("data", "run", "talk") else None)
        results.append(result)
        print(
            f"[{kind} → {result['route']}] {question}\n  searched {result['searches']}, cited {result['cited']}, "
            f"removed {result['removed']}, unverified {result['unverified']}, read "
            f"{len(result['reads'])}, proposed {len(result['proposals'])}, numbers "
            f"{sum(n['status'] == 'verified' for n in result['numbers'])}/{len(result['numbers'])} "
            f"verified, {result['seconds']} s"
        )
    report = {"model": provider.name, "summary": summary(results), "results": results}
    print(json.dumps(report["summary"], indent=2))
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
