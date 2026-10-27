"""Run a fixed set of questions through the assistant and measure how it behaves.

Uses the model named in .env (MAGONIA_MODEL_URL, MAGONIA_MODEL) and live OpenAlex.

    uv run python scripts/evaluate_assistant.py [results.json]

For each question it records whether the model searched, how many papers it found and cited,
how many citations the check removed (invented numbers), author–year mentions it could not
verify, and how long the answer took. Questions are of three kinds:

- research: should be answered from a search, with citations
- chat: greetings and off-topic requests, which should not trigger a search
- trap: questions about papers that do not exist, which must not be "confirmed"
"""

import json
import sys
import time

from engine.assistant import answer, from_environment

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
]


def run(kind: str, question: str, provider) -> dict:
    start = time.time()
    searches, papers, final = [], [], {}
    for event in answer(provider, [{"role": "user", "content": question}]):
        if event["type"] == "search":
            searches.append(event["query"])
        elif event["type"] == "papers":
            papers.extend(event["papers"])
        elif event["type"] == "check":
            final = event
    return {
        "kind": kind,
        "question": question,
        "searches": searches,
        "found": len(papers),
        "cited": final.get("cited", []),
        "removed": final.get("removed", []),
        "unverified": final.get("unverified", []),
        "seconds": round(time.time() - start, 1),
        "answer": final.get("text", ""),
    }


def summary(results: list[dict]) -> dict:
    research = [r for r in results if r["kind"] == "research"]
    chat = [r for r in results if r["kind"] == "chat"]
    return {
        "research questions that searched": f"{sum(bool(r['searches']) for r in research)}/{len(research)}",
        "research answers with at least one checked citation": (
            f"{sum(bool(r['cited']) for r in research)}/{len(research)}"
        ),
        "chat questions that searched (should be 0)": f"{sum(bool(r['searches']) for r in chat)}/{len(chat)}",
        "invented citation numbers removed": sum(len(r["removed"]) for r in results),
        "unverified author-year mentions": sum(len(r["unverified"]) for r in results),
        "median seconds per answer": sorted(r["seconds"] for r in results)[len(results) // 2],
    }


if __name__ == "__main__":
    provider = from_environment()
    results = []
    for kind, question in QUESTIONS:
        result = run(kind, question, provider)
        results.append(result)
        print(
            f"[{kind}] {question}\n  searched {result['searches']}, cited {result['cited']}, "
            f"removed {result['removed']}, unverified {result['unverified']}, {result['seconds']} s"
        )
    report = {"model": provider.name, "summary": summary(results), "results": results}
    print(json.dumps(report["summary"], indent=2))
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
