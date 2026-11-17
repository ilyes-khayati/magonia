"""Controlled evidence: does Magon use the literature it is given as the evidence allows?

    uv run python evaluation/controlled.py run RESULTS_DIR --label after
    PYTHONPATH=<old checkout>/engine/src uv run python evaluation/controlled.py run \
        RESULTS_DIR --label before
    uv run python evaluation/controlled.py score RESULTS_DIR

The same why-question about the reference orchard is asked four times, and each time the search
returns a fixed set of real papers instead of searching (tests/data/controlled_evidence.json):
papers from a matching or near setting, papers on the same topic from other regions and
climates, papers that say nothing about the question, or the first two together. Changing one
evidential condition at a time separates what the pipeline does with evidence from what the
search happened to find, after DeR2 (Ying et al. 2026), NeoQA (Glockner et al. 2025) and the
sufficiency tests of Joren et al. (2024, arXiv 2411.06037).

The papers, their settings and how far each is from an olive orchard in north-western Tunisia
(direct, partial, indirect, off-topic; GRADE indirectness, Guyatt et al. 2025) were labelled by
hand from the abstracts, and the measures below were written, before any version was run on
these cases and before the build they test. Abstracts only: no full text is read, so every
version sees exactly the same evidence.

Measures, per answer:
- misapplied: sentences that cite a paper from another region and climate (indirect) and say
  something of the researcher's own orchard or data in the same sentence. Lower is better.
- cited, in the off-topic condition: sentences that cite a paper at all, when no paper given
  bears on the question. Lower is better.
- says the evidence falls short: the answer states that the papers found do not address the
  question, or come from elsewhere (ABSTAINS). Expected in the mismatched and off-topic
  conditions.
- prefers the near evidence, in the mixed condition: of the citations to papers, the share to
  direct or partial ones. Higher is better.
The part of an answer that code writes from the cited papers' records ("Does the evidence fit
your setting?") is not the model's explanation: the first three measures and the scorer read
the answer without it, and "says the evidence falls short" reads the whole answer, as the
researcher does (decided 17 Nov, before any version producing that part was scored).
- supported: explanation sentences the independent scorer finds supported (OpenAlex abstracts
  and MiniCheck, as evaluation/explanations.py). Expected highest in the matched condition.
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
from cases import DATA, jendouba_view
from explanations import WHERE, evidence_for, explanation_sentences, model_part

from engine.assistant import Ollama, answer
from engine.library import Library
from engine.literature import Paper

CONDITIONS = ["matched", "mismatched", "off-topic", "mixed"]
FIT_NEAR = {"direct", "partial"}

# the researcher's own orchard or data, named in a sentence
OWN = re.compile(
    r"\b(your|my|this|the) (olive )?(orchard|grove|area|site|data|record|series|pixel)s?\b"
    r"|\bhere\b|\bin your\b|\bJendouba\b",
    re.IGNORECASE,
)
# the answer says the papers do not bear on the question, or come from another setting
ABSTAINS = re.compile(
    r"\bno (paper|study|studies|evidence|research)\b|\bnone of the (papers|studies)\b"
    r"|\b(do|does|did) not (directly )?(address|apply|explain|cover|discuss|examine)\b"
    r"|\bnot (directly )?(applicable|relevant|transferable)\b|\b(could|did) not find\b"
    r"|\b(different|another|other) (region|setting|climate|ecosystem|crop|vegetation)s?\b"
    r"|\bmade elsewhere\b|\bfound (in|on) [A-Z]",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[(\d+(?:\s*,\s*p\.\s*\d+)?(?:\s*[,;]\s*\d+(?:\s*,\s*p\.\s*\d+)?)*)\]")


def evidence() -> dict:
    return json.loads((DATA / "controlled_evidence.json").read_text())


def given(case: dict, condition: str) -> list[str]:
    if condition != "mixed":
        return case[condition]
    m, x = case["matched"], case["mismatched"]
    return [p for pair in zip(m, x, strict=True) for p in pair]  # interleaved


def paper(d: dict) -> Paper:
    fields = {k: v for k, v in d.items() if k in Paper.__dataclass_fields__}
    return Paper(**fields)


def olive_view():
    """The reference orchard, named as a researcher would name it and located."""
    view = jendouba_view()
    for s in view.series:
        s.area = "Olive orchard"
    view.context = [
        line.replace("Areas: Orchard", "Areas: Olive orchard") for line in view.context
    ] + [WHERE]
    return view


def run(args) -> None:
    provider = Ollama(
        os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434"),
        os.environ.get("MAGONIA_MODEL", "qwen2.5:7b"),
    )
    import engine

    data = evidence()
    view = olive_view()
    args.results.mkdir(parents=True, exist_ok=True)
    library = Library(args.results / f"papers-{args.label}.db", embed=provider.embed)
    raw = args.results / "raw.jsonl"
    done = set()
    if raw.exists():
        for line in raw.read_text().splitlines():
            r = json.loads(line)
            done.add((r["label"], r["id"], r["condition"]))
    for case in data["cases"]:
        for condition in CONDITIONS:
            if (args.label, case["id"], condition) in done:
                continue
            ids = given(case, condition)
            fixed = [paper(data["papers"][i]) for i in ids]
            record = {
                "label": args.label,
                "id": case["id"],
                "condition": condition,
                "question": case["question"],
                "engine": str(Path(engine.__file__).parent),
                "given": ids,
                "searches": [],
                "numbered": [],
            }
            start = time.time()
            try:
                for event in answer(
                    provider,
                    [{"role": "user", "content": case["question"]}],
                    search=lambda query, fixed=fixed: list(fixed),
                    view=view,
                    library=library,
                ):
                    if event["type"] == "route":
                        record["route"] = event["kind"]
                    elif event["type"] == "search":
                        record["searches"].append(event["query"])
                    elif event["type"] == "papers":
                        record["numbered"] += [[p["n"], p["id"]] for p in event["papers"]]
                    elif event["type"] == "check":
                        for key in ("text", "numbers", "uncited", "support", "withdrawn"):
                            record[key] = event.get(key, [] if key != "text" else "")
                        record["answer"] = record.pop("text")
                        record["settings"] = event.get("settings", [])
                        record["parts"] = event.get("parts", {})
            except Exception as exc:  # noqa: BLE001 - a failed answer is recorded, not fatal
                record["error"] = repr(exc)
            record["seconds"] = round(time.time() - start, 1)
            with raw.open("a") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{args.label} {case['id']} {condition}: {record['seconds']} s", flush=True)


def measures(record: dict, papers: dict) -> dict:
    from engine.honesty import sentences

    fit = {int(n): papers[pid]["gold"]["fit"] for n, pid in record.get("numbered", [])}
    text = model_part(record.get("answer", ""))
    misapplied = cited_sentences = near = far = 0
    for _, _, sentence in sentences(text):
        cited = {
            int(x)
            for group in CITATION.findall(sentence)
            for x in re.split(r"[,;]", group)
            if x.strip().isdigit()
        }
        cited = {n for n in cited if n in fit}
        if not cited:
            continue
        cited_sentences += 1
        near += sum(fit[n] in FIT_NEAR for n in cited)
        far += sum(fit[n] not in FIT_NEAR for n in cited)
        if any(fit[n] == "indirect" for n in cited) and OWN.search(sentence):
            misapplied += 1
    return {
        "misapplied": misapplied,
        "cited": cited_sentences,
        "near": near,
        "far": far,
        "abstains": bool(ABSTAINS.search(record.get("answer", ""))),
    }


def score(args) -> None:
    from engine.verify import judge_for

    judge = judge_for("minicheck-roberta")
    if judge is None:
        raise SystemExit("MiniCheck is not installed: uv sync --extra verify")
    papers = evidence()["papers"]
    raw = [json.loads(line) for line in (args.results / "raw.jsonl").read_text().splitlines()]
    cache_path = args.results / "evidence.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows = []
    for r in raw:
        if "error" in r:
            continue
        r.update(measures(r, papers))
        scored = []
        for sentence in explanation_sentences(r):
            verdicts = [judge(sentence, a) for a in evidence_for(sentence, cache)]
            scored.append({"sentence": sentence, "supported": "yes" in verdicts})
        r["scored"] = scored
        rows.append(r)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
    (args.results / "scored.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    )
    labels = sorted({r["label"] for r in rows}, key=lambda x: (x != "before", x))
    lines = [
        "| condition | measure | " + " | ".join(labels) + " |",
        "|---|---|" + "---|" * len(labels),
    ]

    def of(label, condition):
        return [r for r in rows if r["label"] == label and r["condition"] == condition]

    def supported(rs):
        s = [x["supported"] for r in rs for x in r["scored"]]
        return f"{sum(s)}/{len(s)} ({100 * sum(s) / max(len(s), 1):.0f}%)"

    table = [
        ("matched", "supported (independent scorer)", supported),
        ("matched", "sentences citing a paper, per answer", lambda rs: f"{statistics.mean(r['cited'] for r in rs):.1f}"),
        ("mismatched", "misapplied sentences, per answer", lambda rs: f"{statistics.mean(r['misapplied'] for r in rs):.2f}"),
        ("mismatched", "says the evidence falls short", lambda rs: f"{sum(r['abstains'] for r in rs)}/{len(rs)}"),
        ("off-topic", "sentences citing a paper, per answer", lambda rs: f"{statistics.mean(r['cited'] for r in rs):.1f}"),
        ("off-topic", "says the evidence falls short", lambda rs: f"{sum(r['abstains'] for r in rs)}/{len(rs)}"),
        ("mixed", "citations to near papers", lambda rs: f"{sum(r['near'] for r in rs)}/{sum(r['near'] + r['far'] for r in rs)}"),
        ("mixed", "misapplied sentences, per answer", lambda rs: f"{statistics.mean(r['misapplied'] for r in rs):.2f}"),
        ("all", "seconds per answer", lambda rs: f"{statistics.mean(r['seconds'] for r in rs):.0f}"),
    ]  # fmt: skip
    for condition, name, f in table:
        cells = []
        for label in labels:
            rs = (
                [r for r in rows if r["label"] == label]
                if condition == "all"
                else of(label, condition)
            )
            cells.append(f(rs) if rs else "–")
        lines.append(f"| {condition} | {name} | " + " | ".join(cells) + " |")
    (args.results / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["run", "score"])
    parser.add_argument("results", type=Path)
    parser.add_argument("--label", default="after")
    args = parser.parse_args()
    run(args) if args.step == "run" else score(args)


if __name__ == "__main__":
    main()
