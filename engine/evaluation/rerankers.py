"""Does a cross-encoder rank papers better than the embedding does? Measured on papers already judged.

    uv run --extra verify python evaluation/rerankers.py OUT_DIR RESULTS_DIR [RESULTS_DIR ...]

Magon ranks the candidates OpenAlex returns by the cosine similarity between the question
and each paper (rank.py), computed separately: the two embeddings never meet. That measures
topic, not usefulness: two West Nile fever papers scored 0.76 for a question about Tunisian
NDVI because they share "Tunisia" and "remote sensing". A cross-encoder reads the question
and the paper together and scores how well the one answers the other, which is the question
the ranking should ask.

The papers to measure on come from evaluation runs: each paper a system was given, with the
scorer's judgement of whether it helps answer the question (yes, partly, no), kept in the
run's cache.json. The judge was the chat model, and the useless papers are few, so this says
which ranking is better, not by how much.

For the embedding (the relevance Magon stored) and for each cross-encoder: the AUC for
telling useless papers from the rest, and at the cutoff that keeps 95% of the useful ones,
the share of useless papers dropped, with the seconds per pair on this machine.

Writes OUT_DIR/rerankers.md and rerankers.json.

Measured on 13 November 2026 (reports/reranker-results), on the 100 papers of the labelling
run, 11 of them useless: AUC 0.77 for the embedding, 0.78 for MiniLM, 0.79 for BGE-base; at
the cutoff keeping 95% of the useful papers the embedding dropped 45% of the useless ones,
the cross-encoders 27%. No gain for 0.1–0.5 s per pair, so Magon keeps ranking by embedding.
Those papers are the embedding's own survivors (none below its floor reached the judge),
which favours it; the comparison is worth repeating on candidates taken before the floor.
"""

import argparse
import json
import time
from pathlib import Path

from sklearn.metrics import roc_auc_score

CROSS_ENCODERS = {
    "minilm": "cross-encoder/ms-marco-MiniLM-L-6-v2",  # 22M parameters, trained on web search
    "bge-base": "BAAI/bge-reranker-base",  # 278M parameters, multilingual
}
KEEP_USEFUL = 0.95


def judged(folders: list[Path]) -> list[dict]:
    """Each paper given in a run, once per question, with its judgement and stored relevance."""
    items: dict[tuple[str, str], dict] = {}
    for folder in folders:
        cache = json.loads((folder / "cache.json").read_text())
        for line in (folder / "raw.jsonl").read_text().splitlines():
            r = json.loads(line)
            for p in r.get("papers", []):
                verdict = cache.get(f"relevance|{r['question']}|{p['title']}")
                if verdict is None or not p.get("abstract"):
                    continue
                items[(r["question"], p["title"])] = {
                    "question": r["question"],
                    "text": f"{p['title']}. {p['abstract']}",
                    "useful": int(verdict != "no"),
                    "embedding": p.get("relevance"),
                }
    return list(items.values())


def cross_encoder(model_id: str):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id)
    model.eval()

    def score(pairs: list[tuple[str, str]]) -> list[float]:
        out = []
        with torch.no_grad():
            for i in range(0, len(pairs), 8):
                batch = pairs[i : i + 8]
                inputs = tokenizer(
                    [q for q, _ in batch],
                    [t for _, t in batch],
                    truncation="only_second",
                    max_length=512,
                    padding=True,
                    return_tensors="pt",
                )
                logits = model(**inputs).logits
                out += [float(x) for x in logits.view(-1)]
        return out

    return score


def measure(useful: list[int], scores: list[float]) -> dict:
    kept = sorted(s for s, u in zip(scores, useful, strict=True) if u)
    cutoff = kept[int((1 - KEEP_USEFUL) * len(kept))]
    useless = [s for s, u in zip(scores, useful, strict=True) if not u]
    return {
        "auc": roc_auc_score(useful, scores) if len(set(useful)) > 1 else None,
        "cutoff": cutoff,
        "useless_dropped": sum(s < cutoff for s in useless) / len(useless) if useless else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--models", default=",".join(CROSS_ENCODERS))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    items = judged(args.results)
    useful = [i["useful"] for i in items]
    results = {"n": len(items), "useless": useful.count(0), "rankers": {}}
    scored = {"useful": useful, "embedding": [i["embedding"] for i in items]}
    results["rankers"]["embedding"] = {**measure(useful, scored["embedding"]), "seconds_per_pair": 0}
    for name in args.models.split(","):
        started = time.time()
        scores = cross_encoder(CROSS_ENCODERS[name])([(i["question"], i["text"]) for i in items])
        m = measure(useful, scores)
        m["seconds_per_pair"] = (time.time() - started) / len(items)
        results["rankers"][name] = m
        scored[name] = scores
        print(f"{name}: AUC {m['auc']:.2f}, useless dropped {m['useless_dropped']:.0%}", flush=True)

    lines = [
        "# Rankers compared",
        "",
        f"{results['n']} papers judged by the chat model, {results['useless']} of them useless.",
        "",
        "| Ranker | AUC (useless vs rest) | Cutoff keeping 95% of useful | Useless dropped | s / pair |",
        "|---|---|---|---|---|",
    ]
    for name, m in results["rankers"].items():
        auc = "–" if m["auc"] is None else f"{m['auc']:.2f}"
        dropped = "–" if m["useless_dropped"] is None else f"{m['useless_dropped']:.0%}"
        lines.append(
            f"| {name} | {auc} | {m['cutoff']:.3f} | {dropped} | {m['seconds_per_pair']:.2f} |"
        )
    lines += [
        "",
        (
            "Labels come from the chat model's judgement of each paper, and the useless papers "
            "are few: a direction, not a result. The cutoff is chosen and measured on the same "
            "papers."
        ),
        "",
    ]
    (args.out / "rerankers.md").write_text("\n".join(lines))
    (args.out / "rerankers.json").write_text(json.dumps(results, indent=1))
    (args.out / "scores.json").write_text(json.dumps(scored))
    print(args.out / "rerankers.md")


if __name__ == "__main__":
    main()
