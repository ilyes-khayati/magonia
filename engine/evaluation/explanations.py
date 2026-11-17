"""Explanations of the researcher's data: does Magon explain from evidence, and say when it does
not? Run the same questions through two versions of the pipeline, then score both the same way.

    uv run python evaluation/explanations.py run RESULTS_DIR --label after [--repeats 2]
    PYTHONPATH=<old checkout>/engine/src uv run python evaluation/explanations.py run \
        RESULTS_DIR --label before
    uv run python evaluation/explanations.py score RESULTS_DIR

The questions ask why the reference orchard's data look as they do. They were written before
either version was run, and none was used while building the explanation step.

Scoring is independent of both pipelines, after SAFE (Wei et al. 2024, arXiv 2403.18802) and
VeriScore (Song et al. 2024, arXiv 2406.19276): the answer is cut into sentences; a sentence
whose numbers code verified against the workspace is a fact of the data and set aside; every
other sentence of some length is an explanation, searched for on its own in OpenAlex, and
judged by MiniCheck against the abstracts found. Supported means one abstract bears it out.
SAFE searches Google and VeriScore Google snippets; here the scholarly index and its abstracts
stand in, so "not supported" can mean wrong or only that no abstract says it (VeriScore states
the same limit). The share supported is the explanation's precision.

For the version that labels its own reasoning, how often its label agrees with the independent
scorer is reported too: a sentence it calls its own reasoning that the scorer finds supported,
or one it calls supported that the scorer does not.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cases import jendouba_view

from engine.assistant import Ollama, answer
from engine.library import Library

QUESTIONS = [
    ("w01", "Why is NDVI lowest in July in my orchard?"),
    ("w02", "Why does NDVI peak in March here?"),
    ("w03", "Why does NDVI fall when LST rises in my orchard?"),
    ("w04", "What could explain the year with the lowest NDVI here?"),
    ("w05", "Why is NDVI correlated with SPEI-3 in my orchard?"),
    ("w06", "How do you interpret the seasonal cycle of NDVI in my orchard?"),
    ("w07", "Why does the NDVI swing so much within the year here?"),
    ("w08", "What could cause the most unusual month in the NDVI series?"),
    ("w09", "Why does greenness rise so fast in autumn here?"),
    ("w10", "Explain why the NDVI trend is not significant."),
    ("w11", "Why would drought lower NDVI with a delay of a few months?"),
    ("w12", "What does the correlation between NDVI and SPEI tell me about my orchard?"),
]

# A second set, written on 16 Nov before the setting check was built and never used while
# building it: asked of the version before the check and the version after it. The orchard
# is located for both (WHERE), as the platform now tells Magon where the areas lie, so that
# what differs between the two versions is the pipeline alone
SECOND = [
    ("n01", "Why does the orchard's NDVI drop so sharply in May?"),
    ("n02", "What might explain why NDVI is higher in winter than in summer here?"),
    ("n03", "How should I interpret the negative correlation between NDVI and LST in my orchard?"),
    ("n04", "Is there a reason NDVI responds to SPEI with a delay in this orchard?"),
    ("n05", "What could be behind the low NDVI years in my record?"),
    ("n06", "Explain why 2010 has the lowest annual NDVI in my orchard."),
    ("n07", "What does the seasonal amplitude of NDVI tell me about this orchard?"),
    ("n08", "Why is the summer NDVI so stable from June to September here?"),
    ("n09", "What might cause NDVI to rise again in autumn in my orchard?"),
    ("n10", "How come LST matters more than SPEI for NDVI here?"),
    ("n11", "What does the lag between drought and greenness tell me about my orchard?"),
    ("n12", "Why would this orchard's NDVI peak in early spring?"),
    ("n13", "Explain why NDVI and SPEI-3 move together in this orchard."),
    ("n14", "What could explain a weak long-term NDVI trend in my orchard?"),
    ("n15", "Why does the NDVI of my orchard vary so much from year to year?"),
    ("n16", "What are the reasons behind the hot-season NDVI minimum here?"),
]
SETS = {"first": QUESTIONS, "second": SECOND}
# where the reference orchard lies, as the platform says it (centroid of its polygon)
WHERE = "The areas lie near 36.51° N, 8.56° E."

MIN_WORDS = 6  # a shorter sentence is a heading or a framing, not an explanation
# what research is said to have found, with no paper named (as engine.honesty, kept here so
# the old version is scored by the same rule)
RESEARCH_SAYS = re.compile(
    r"\b(studies|research|researchers|the literature|(a|an|one|previous|recent|several|many|some)"
    r"\s+(\d{4}\s+)?(\w+\s+)?(study|studies|paper|papers))\s+(\w+\s+){0,6}?(have\s+|has\s+)?"
    r"(shown|show|shows|found|finds|indicated?|indicates|suggests?|reported|reports?|"
    r"demonstrated?|revealed|observed)\b|\baccording to (the )?(literature|studies|research)\b",
    re.IGNORECASE,
)


def run(args) -> None:
    provider = Ollama(
        os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434"),
        os.environ.get("MAGONIA_MODEL", "qwen2.5:7b"),
    )
    import engine

    view = jendouba_view()
    if args.set == "second":
        view.context.append(WHERE)
    args.results.mkdir(parents=True, exist_ok=True)
    library = Library(args.results / f"papers-{args.label}.db", embed=provider.embed)
    raw = args.results / "raw.jsonl"
    done = set()
    if raw.exists():
        for line in raw.read_text().splitlines():
            r = json.loads(line)
            done.add((r["label"], r["id"], r["repeat"]))
    for repeat in range(1, args.repeats + 1):
        for qid, question in SETS[args.set]:
            if (args.label, qid, repeat) in done:
                continue
            record = {"label": args.label, "id": qid, "repeat": repeat, "question": question}
            record["engine"] = str(Path(engine.__file__).parent)
            record["searches"], record["papers"] = [], []
            start = time.time()
            try:
                for event in answer(
                    provider,
                    [{"role": "user", "content": question}],
                    view=view,
                    library=library,
                ):
                    if event["type"] == "route":
                        record["route"] = event["kind"]
                    elif event["type"] == "search":
                        record["searches"].append(event["query"])
                    elif event["type"] == "papers":
                        record["papers"] += [p["short"] for p in event["papers"]]
                    elif event["type"] == "check":
                        record["answer"] = event.get("text", "")
                        record["numbers"] = event.get("numbers", [])
                        record["uncited"] = event.get("uncited", [])
                        record["support"] = event.get("support", [])
                        record["withdrawn"] = event.get("withdrawn", [])
                        record["settings"] = event.get("settings", [])
            except Exception as exc:  # noqa: BLE001 - a failed answer is recorded, not fatal
                record["error"] = repr(exc)
            record["seconds"] = round(time.time() - start, 1)
            with raw.open("a") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{args.label} {qid} #{repeat}: {record['seconds']} s", flush=True)


# the parts of an answer that code writes: whether each cited paper fits (engine.fit.summary)
# and each explanation's test on the data (engine.claims.tested_part):
# not the model's explanation, so not scored as one (decided 17 Nov, before any version
# producing it was scored)
CODE_PARTS = ("**Does the evidence fit your setting", "**Tested on your data**")


# a mark code adds after a sentence that applies a far paper to the researcher's data
TRANSFER_MARK = re.compile(r"\s*\*\(This applies a finding from a far setting.*?\)\*", re.DOTALL)


def model_part(text: str) -> str:
    """What the model wrote: the parts code writes, and the marks it adds, are left out."""
    for heading in CODE_PARTS:
        text = text.split(heading)[0]
    return TRANSFER_MARK.sub("", text)


def explanation_sentences(record: dict) -> list[str]:
    from engine.honesty import sentences

    text = model_part(record.get("answer", ""))
    verified = [n for n in record.get("numbers", []) if n["status"] == "verified"]
    out = []
    for start, end, sentence in sentences(text):
        if any(start <= n["start"] < end for n in verified):
            continue  # a fact of the data, checked as a number
        plain = re.sub(r"\[[^\]]*\]|\*\*|^[-*#\d.)\s]+", "", sentence).strip()
        if len(re.findall(r"[A-Za-z]{3,}", plain)) >= MIN_WORDS and plain.endswith("."):
            out.append(plain)
    return out


def evidence_for(sentence: str, cache: dict) -> list[str]:
    from engine.literature import LiteratureError, keywords, search_papers

    query = keywords(sentence)
    if query not in cache:
        try:
            # one index for every version scored: no Crossref fallback in the scorer
            cache[query] = [
                p.abstract for p in search_papers(query, limit=5, fallback=False) if p.abstract
            ]
        except LiteratureError:
            cache[query] = None
            time.sleep(2)
    return cache[query] or []


def score(args) -> None:
    from engine.verify import judge_for

    judge = judge_for("minicheck-roberta")
    if judge is None:
        raise SystemExit("MiniCheck is not installed: uv sync --extra verify")
    raw = [json.loads(line) for line in (args.results / "raw.jsonl").read_text().splitlines()]
    cache_path = args.results / "evidence.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows = []
    for r in raw:
        if "error" in r:
            continue
        own = {s["claim"].strip(" -*#:"): s["status"] for s in r.get("uncited", [])}
        scored = []
        for sentence in explanation_sentences(r):
            abstracts = evidence_for(sentence, cache)
            verdicts = [judge(sentence, a) for a in abstracts]
            supported = "yes" in verdicts
            label = next((v for k, v in own.items() if k and (k in sentence or sentence in k)), "")
            scored.append({"sentence": sentence, "supported": supported, "label": label})
        r["scored"] = scored
        r["research_says"] = len(RESEARCH_SAYS.findall(r.get("answer", "")))
        rows.append(r)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    (args.results / "scored.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    )

    lines = ["| | before | after |", "|---|---|---|"]

    def by(label):
        return [r for r in rows if r["label"] == label]

    def cell(label, f):
        return f(by(label)) if by(label) else "–"

    def precision(rs):
        s = [x["supported"] for r in rs for x in r["scored"]]
        per = [
            sum(x["supported"] for x in r["scored"]) / len(r["scored"]) for r in rs if r["scored"]
        ]
        sd = statistics.stdev(per) if len(per) > 1 else 0
        return f"{sum(s)}/{len(s)} ({100 * sum(s) / max(len(s), 1):.0f}%), per answer sd {sd:.2f}"

    def mean_of(key):
        return lambda rs: f"{statistics.mean(r[key] for r in rs):.1f}"

    metrics = [
        ("answers", lambda rs: str(len(rs))),
        ("searched the literature", lambda rs: f"{sum(bool(r['searches']) for r in rs)}"),
        ("explanation sentences per answer", lambda rs: f"{statistics.mean(len(r['scored']) for r in rs):.1f}"),
        ("explanation sentences supported (independent scorer)", precision),
        ("'studies show' with no paper named, per answer", lambda rs: f"{statistics.mean(r['research_says'] for r in rs):.2f}"),
        ("sentences withdrawn by Magon, per answer", lambda rs: f"{statistics.mean(len(r.get('withdrawn', [])) for r in rs):.1f}"),
        ("sentences where Magon named another setting, per answer", lambda rs: f"{statistics.mean(len(r.get('settings', [])) for r in rs):.2f}"),
        ("seconds per answer (mean)", mean_of("seconds")),
    ]  # fmt: skip
    for name, f in metrics:
        lines.append(f"| {name} | {cell('before', f)} | {cell('after', f)} |")

    # agreement of the new version's own labels with the independent scorer
    labelled = [x for r in by("after") for x in r["scored"] if x["label"]]
    if labelled:
        own = [x for x in labelled if x["label"] == "unsourced"]
        backed = [x for x in labelled if x["label"] == "supported"]
        lines += [
            "",
            f"After: {len(labelled)} explanation sentences carried Magon's own label.",
            (
                f"- labelled own reasoning: {len(own)}; of these the independent scorer found "
                f"{sum(x['supported'] for x in own)} supported"
            ),
            (
                f"- labelled supported by a paper found: {len(backed)}; of these the scorer "
                f"found {sum(x['supported'] for x in backed)} supported"
            ),
        ]
    (args.results / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["run", "score"])
    parser.add_argument("results", type=Path)
    parser.add_argument("--label", default="after")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--set", choices=list(SETS), default="first")
    args = parser.parse_args()
    run(args) if args.step == "run" else score(args)


if __name__ == "__main__":
    main()
