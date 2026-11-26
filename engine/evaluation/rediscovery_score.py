"""Score the rediscovery runs against the researcher's answer key, then hand them the matches.

    uv run python evaluation/rediscovery_score.py RESULTS_DIR [--key evaluation/rediscovery_key.json]

The key, written before any run, states the finding as short claims, region by region:

    {"written": "2026-11-15", "by": "…", "regions": {"Jendouba": ["NDVI peaks in late winter
    or spring.", "…"], "Sfax": […]}}

As in FIRE-Bench, the answer and the key are compared claim by claim. Recall is the share of the
key's claims the answer states: a key claim counts as found when MiniCheck finds it supported
by one sentence of the answer (premise the sentence, claim the key's), so the matching is done
by a verifier, never by the model that answered. Each run is scored on its own and the runs of
a region and condition are given as mean ± standard deviation, because answers vary from run
to run.

The verifier has never seen this kind of text (it was measured on SciFact), so every match
and every miss goes into RESULTS_DIR/hand_check.csv with an empty column for the researcher,
who checks them all: with 4 regions × 2 conditions × 3 runs there are few enough. The report
gives the verifier's score and the researcher's, and how often they agreed.
"""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from engine.honesty import sentences
from engine.verify import judge_for


def best_sentence(answer: str, claim: str, judge) -> tuple[str, str]:
    """The answer's sentence that best states the claim, and the verifier's verdict on it."""
    best = ("", "no")
    for _, _, sentence in sentences(answer):
        verdict = judge(claim, sentence)
        if verdict == "yes":
            return sentence, "yes"
        if verdict == "partly" and best[1] == "no":
            best = (sentence, "partly")
    return best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--key", type=Path, default=Path(__file__).parent / "rediscovery_key.json")
    parser.add_argument("--verifier", default="minicheck-roberta")
    args = parser.parse_args()

    key = json.loads(args.key.read_text())
    judge = judge_for(args.verifier)
    if judge is None:
        raise SystemExit(f"{args.verifier} is not installed: uv sync --extra verify")
    runs = [json.loads(line) for line in (args.results / "raw.jsonl").read_text().splitlines()]

    recall: dict[tuple[str, str], list[float]] = defaultdict(list)
    rows = []
    for r in runs:
        claims = key["regions"].get(r["region"], [])
        if not claims:
            continue
        found = 0
        for claim in claims:
            sentence, verdict = best_sentence(r["answer"], claim, judge)
            found += verdict == "yes"
            rows.append(
                {
                    "region": r["region"],
                    "condition": r["condition"],
                    "run": r["run"],
                    "key claim": claim,
                    "closest sentence": sentence,
                    "verifier": verdict,
                    "researcher (yes/no)": "",
                }
            )
        recall[(r["region"], r["condition"])].append(found / len(claims))

    with (args.results / "hand_check.csv").open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        f"Rediscovery, scored by {args.verifier} against the key written {key.get('written')}",
        "",
        "| Region | Condition | Runs | Recall (mean ± sd) |",
        "|---|---|---|---|",
    ]
    for (region, condition), values in sorted(recall.items()):
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
        mean = statistics.mean(values)
        lines.append(f"| {region} | {condition} | {len(values)} | {mean:.2f} ± {sd:.2f} |")
    (args.results / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
