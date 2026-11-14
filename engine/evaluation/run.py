"""Run every case through every system it applies to, several times, and keep what happened.

    uv run python evaluation/run.py RESULTS_DIR [--repeats 2] [--only r01,d03] [--systems bare]

Uses the model named by MAGONIA_MODEL_URL and MAGONIA_MODEL, live OpenAlex and live
publishers. Each answer is one line of RESULTS_DIR/raw.jsonl, written as soon as it is done,
so a run that stops can be started again and continues where it was. The libraries (papers
read in full, the two test files) are kept in RESULTS_DIR too, never in ~/.magonia.

Answers are scored afterwards by score.py, so the scoring can change without asking the
model again.
"""

import argparse
import json
import os
import time
import traceback
from pathlib import Path

from cases import CASES, gold, jendouba_view
from systems import file_library, run

from engine.assistant import Ollama
from engine.library import Library


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--only", default="", help="case ids, comma separated")
    parser.add_argument("--systems", default="", help="system names, comma separated")
    parser.add_argument(
        "--set",
        choices=["developer", "held-out", "all"],
        default="all",
        help="the developer's cases, the researcher's held-out questions, or both",
    )
    args = parser.parse_args()

    url = os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434")
    model = os.environ.get("MAGONIA_MODEL", "qwen2.5:7b")
    provider = Ollama(url, model)
    view = jendouba_view()
    gold(view)

    args.results.mkdir(parents=True, exist_ok=True)
    raw = args.results / "raw.jsonl"
    done = set()
    if raw.exists():
        for line in raw.read_text().splitlines():
            r = json.loads(line)
            done.add((r["case"], r["system"], r["repeat"]))
    libraries = {
        "papers": Library(args.results / "papers.db", embed=provider.embed),
        "files": file_library(args.results / "files.db", provider.embed),
    }
    only = set(filter(None, args.only.split(",")))
    systems = set(filter(None, args.systems.split(",")))
    todo = [
        (case, system, repeat)
        for repeat in range(1, args.repeats + 1)
        for case in CASES
        for system in case.systems
        if (not only or case.id in only)
        and (args.set == "all" or (case.kind == "held-out") == (args.set == "held-out"))
        and (not systems or system in systems)
        and (case.id, system, repeat) not in done
    ]
    print(f"{len(todo)} answers to get ({len(done)} already done) from {model} at {url}")
    started = time.time()
    for i, (case, system, repeat) in enumerate(todo, 1):
        try:
            record = run(provider, system, case, view, libraries)
            error = None
        except Exception as exc:  # noqa: BLE001 - one failed answer must not stop the run
            record, error = {}, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        line = {
            "case": case.id,
            "kind": case.kind,
            "system": system,
            "repeat": repeat,
            "model": model,
            "question": case.question,
            "turns": list(case.turns),
            "error": error,
            **record,
        }
        with raw.open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        elapsed = time.time() - started
        print(
            f"[{i}/{len(todo)}] {case.id} {system} #{repeat}: "
            f"{'ERROR ' + error.splitlines()[0] if error else str(record.get('seconds')) + ' s'}"
            f" · {elapsed / 60:.0f} min so far, about {elapsed / i * (len(todo) - i) / 60:.0f} left",
            flush=True,
        )


if __name__ == "__main__":
    main()
