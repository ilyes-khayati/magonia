"""Which verifier to trust: each one scored on the same claims, against labels made by people.

    uv run --extra verify python evaluation/verifiers.py OUT_DIR --scifact DATA_DIR
        [--verifiers nli,minicheck-roberta,minicheck-deberta,model]

Two sets of claims:

- SciFact (Wadden et al., 2020): scientific claims, each with the abstract it was checked
  against, labelled by experts as supported, contradicted, or not enough information. The
  dev split is used (300 claims). Licence CC BY-NC 2.0: used for evaluation, not shipped.
- next, once the sheets are filled: statements from Magon's own answers, labelled by people
  (labels.py), each with the passages it was judged against.

The question asked of each verifier is the one the support check needs: does the passage
support the claim, yes or no. For each verifier: the area under the ROC curve (how well its
probability separates supported from not, whatever the threshold, 0.5 = chance), and at its
best threshold the balanced accuracy and Cohen's κ against the labels. "model" is the chat
model asked in one word, as the support check does today; it gives a verdict, not a
probability, so its yes counts as 1, partly as 0.5, no as 0.

Writes OUT_DIR/verifiers.md and OUT_DIR/verifiers.json.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))

from engine.support import judge_with
from engine.verify import VERIFIERS, load

LEVEL = {"yes": 1.0, "partly": 0.5, "no": 0.0}


def scifact(folder: Path) -> list[dict]:
    """Each dev claim with each abstract it cites: supported (1) or not (0)."""
    corpus = {}
    for line in (folder / "corpus.jsonl").read_text().splitlines():
        doc = json.loads(line)
        corpus[str(doc["doc_id"])] = f"{doc['title']}. " + " ".join(doc["abstract"])
    items = []
    for line in (folder / "claims_dev.jsonl").read_text().splitlines():
        claim = json.loads(line)
        for doc in claim["cited_doc_ids"]:
            found = claim["evidence"].get(str(doc), [])
            label = found[0]["label"] if found else "NOT ENOUGH INFO"
            items.append(
                {
                    "claim": claim["claim"],
                    "passage": corpus[str(doc)],
                    "label": label,
                    "supported": int(label == "SUPPORT"),
                }
            )
    return items


def model_judge():
    from score import judge_stream

    url = os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434")
    model = os.environ.get("MAGONIA_MODEL", "qwen2.5:7b")
    return judge_with(judge_stream(url, model))


def scores(name: str, items: list[dict]) -> list[float]:
    if name == "model":
        judge = model_judge()
        return [LEVEL[judge(i["claim"], i["passage"])] for i in items]
    return load(name).support([(i["passage"], i["claim"]) for i in items])


def best_threshold(truth: list[int], probs: list[float]) -> float:
    """The threshold with the best balanced accuracy, among the probabilities themselves."""
    candidates = sorted(set(probs) | {0.5})
    return max(
        candidates,
        key=lambda t: balanced_accuracy_score(truth, [int(p >= t) for p in probs]),
    )


def measure(truth: list[int], probs: list[float]) -> dict:
    t = best_threshold(truth, probs)
    said = [int(p >= t) for p in probs]
    return {
        "auc": roc_auc_score(truth, probs) if len(set(truth)) > 1 else None,
        "threshold": t,
        "balanced_accuracy": balanced_accuracy_score(truth, said),
        "kappa": cohen_kappa_score(truth, said),
        "at_0.5": balanced_accuracy_score(truth, [int(p >= 0.5) for p in probs]),
    }


def fmt(x) -> str:
    return "–" if x is None else f"{x:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--scifact", type=Path, required=True)
    parser.add_argument("--verifiers", default=",".join([*VERIFIERS, "model"]))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    sets = {"SciFact dev": scifact(args.scifact)}

    results: dict = {}
    for set_name, items in sets.items():
        truth = [i["supported"] for i in items]
        results[set_name] = {"n": len(items), "supported": sum(truth), "verifiers": {}}
        for name in args.verifiers.split(","):
            started = time.time()
            probs = scores(name, items)
            m = measure(truth, probs)
            m["seconds_per_claim"] = (time.time() - started) / len(items)
            results[set_name]["verifiers"][name] = m
            print(f"{set_name} · {name}: AUC {fmt(m['auc'])}, κ {fmt(m['kappa'])}", flush=True)

    lines = ["# Verifiers compared", ""]
    for set_name, r in results.items():
        lines += [
            f"## {set_name}",
            "",
            f"{r['n']} claim–passage pairs, {r['supported']} supported.",
            "",
            "| Verifier | AUC | Best threshold | Balanced accuracy | κ | Balanced accuracy at 0.5 | s / claim |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, m in r["verifiers"].items():
            lines.append(
                f"| {name} | {fmt(m['auc'])} | {fmt(m['threshold'])} | "
                f"{fmt(m['balanced_accuracy'])} | {fmt(m['kappa'])} | {fmt(m['at_0.5'])} | "
                f"{m['seconds_per_claim']:.2f} |"
            )
        lines.append("")
    (args.out / "verifiers.md").write_text("\n".join(lines))
    (args.out / "verifiers.json").write_text(json.dumps(results, indent=1))
    print(args.out / "verifiers.md")


if __name__ == "__main__":
    main()
