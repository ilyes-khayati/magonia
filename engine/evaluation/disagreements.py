"""Where the verifiers and the chat model disagree, on Magon's own statements.

    uv run --extra verify python evaluation/disagreements.py RESULTS_DIR [--thresholds FILE]

Before people have labelled any statement, this shows how often each verifier reaches the
same verdict as the chat model that judges today, and lists the statements where they part.
Those are the cases worth reading first, and the ones the human labels will settle.

A statement's verdict is supported when any of its passages supports it, as in the support
check. A verifier says supported at its threshold: from FILE (the verifiers.json written by
verifiers.py, best threshold on SciFact) when given, else 0.5.

Writes RESULTS_DIR/disagreements.md.
"""

import argparse
import json
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from engine.verify import VERIFIERS, load


def statements(folder: Path) -> list[dict]:
    found = []
    for line in (folder / "scored.jsonl").read_text().splitlines():
        r = json.loads(line)
        for s in r.get("statements", []):
            if s.get("evidence") and s.get("pool") in ("supported", "partly", "unsupported"):
                found.append({"system": r["system"], "case": r["case"], **s})
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--thresholds", type=Path)
    args = parser.parse_args()
    thresholds = {}
    if args.thresholds:
        sets = json.loads(args.thresholds.read_text())
        thresholds = {k: v["threshold"] for k, v in next(iter(sets.values()))["verifiers"].items()}

    items = statements(args.results)
    judge = [int(i["pool"] == "supported") for i in items]
    lines = [
        "# Verifiers against the chat model, on Magon's statements",
        "",
        f"{len(items)} statements with passages, {sum(judge)} judged supported by the chat model.",
        "",
        "| Verifier | Threshold | Says supported | Same verdict as the chat model | κ |",
        "|---|---|---|---|---|",
    ]
    details = []
    for name in VERIFIERS:
        verifier = load(name)
        t = thresholds.get(name, 0.5)
        best = []
        for i in items:
            probs = verifier.support([(p, i["claim"]) for p in i["evidence"]])
            best.append(max(probs))
        said = [int(p >= t) for p in best]
        same = sum(a == b for a, b in zip(said, judge)) / len(items) if items else 0
        lines.append(
            f"| {name} | {t:.2f} | {sum(said)} | {100 * same:.0f}% | "
            f"{cohen_kappa_score(judge, said) if items else 0:.2f} |"
        )
        apart = [(i, p) for i, p, s, j in zip(items, best, said, judge) if s != j]
        details += [f"## {name}: {len(apart)} statements where it differs", ""]
        for i, p in sorted(apart, key=lambda x: -abs(x[1] - t))[:15]:
            details += [
                f"- **{i['claim']}** ({i['system']}, {i['case']})",
                f"  - chat model: {i['pool']}; {name}: {p:.2f}",
                f"  - passage: {i['evidence'][0][:300]}…",
            ]
        details.append("")
        print(f"{name}: {100 * same:.0f}% same verdict", flush=True)
    (args.results / "disagreements.md").write_text("\n".join(lines + [""] + details))
    print(args.results / "disagreements.md")


if __name__ == "__main__":
    main()
