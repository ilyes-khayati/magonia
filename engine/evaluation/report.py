"""Tables from a scored run: each system side by side, then every failure with its answer.

    uv run python evaluation/report.py RESULTS_DIR

Writes RESULTS_DIR/report.md and RESULTS_DIR/summary.json.
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from cases import EVERY

KINDS = [
    ("research", "Literature questions"),
    ("trap", "Papers that do not exist"),
    ("scope", "Outside Magonia's field"),
    ("chat", "Conversation"),
    ("data", "Questions on the researcher's data"),
    ("run", "Asking for an analysis"),
    ("talk", "Talking without wanting an analysis"),
    ("files", "The researcher's own files"),
    ("injection", "An instruction hidden in a file"),
    ("instructions", "Following the researcher's instructions"),
    ("follow-up", "Follow-up questions"),
    ("french", "Questions in French"),
    ("claims", "A paper's claim tested on the researcher's data"),
    ("held-out", "Held out: a researcher's own questions, never tuned on"),
]


def share(hits: int, total: int) -> str:
    return f"{hits}/{total} ({100 * hits / total:.0f}%)" if total else "–"


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> None:
    folder = Path(sys.argv[1])
    scored = [json.loads(line) for line in (folder / "scored.jsonl").read_text().splitlines()]
    raw = {
        (r["case"], r["system"], r["repeat"]): r
        for r in map(json.loads, (folder / "raw.jsonl").read_text().splitlines())
    }
    found = {r["system"] for r in scored}
    # the four systems in their order, then any other run compared with them (e.g. after a change)
    systems = [s for s in EVERY if s in found] + sorted(found - set(EVERY))
    by = defaultdict(list)
    for r in scored:
        by[r["system"]].append(r)
    summary: dict = {}
    out = [f"# Magonia evaluation: {folder.name}", ""]
    errors = [r for r in scored if r["error"]]
    out.append(
        f"{len(scored)} answers, {len(errors)} failed to run; "
        f"{len({r['repeat'] for r in scored})} repeat(s) of each question."
    )

    # Behaviour: the share of answers that did everything the case expects
    rows = []
    for kind, label in KINDS:
        row = [label]
        for s in systems:
            done = [r for r in by[s] if r["kind"] == kind and r.get("passed") is not None]
            row.append(share(sum(r["passed"] for r in done), len(done)))
            summary.setdefault("passed", {}).setdefault(s, {})[kind] = [
                sum(r["passed"] for r in done),
                len(done),
            ]
        rows.append(row)
    out += ["", "## Did the answer do what it should?", ""]
    out.append(table(["Questions", *systems], rows))

    # The literature
    rows = []
    metrics: dict[str, dict] = defaultdict(dict)
    for s in systems:
        lit = [r for r in by[s] if "statements" in r]
        refs = [m["found"] for r in by[s] for m in r.get("mentions", [])] + [
            t["found"] for r in by[s] for t in r.get("titles", [])
        ]
        made_up = [
            r
            for r in by[s]
            if any(m["found"] is False for m in r.get("mentions", []))
            or any(t["found"] is False for t in r.get("titles", []))
        ]
        statements = [x["pool"] for r in lit for x in r["statements"]]
        own = [x for r in lit for x in r.get("own_support", [])]
        relevance = [x for r in lit for x in r.get("relevance", [])]
        pages = sum(r.get("page_citations", 0) for r in lit)
        cites = sum(r.get("all_citations", 0) for r in lit)
        m = metrics[s]
        m["answers with a made-up reference"] = share(len(made_up), len(by[s]))
        checked = [x for x in refs if x is not None]
        m["references written, made up"] = share(checked.count(False), len(checked))
        if len(checked) < len(refs):
            m["references not checked yet (OpenAlex budget spent)"] = str(len(refs) - len(checked))
        m["statements per literature answer"] = f"{len(statements) / len(lit):.1f}" if lit else "–"
        # who judged support: a verifier, or the chat model grading itself (older runs)
        judges = ", ".join(sorted({r.get("judge", "model") for r in lit})) or "model"
        m[f"statements supported by the literature found (judge: {judges})"] = share(
            statements.count("supported"), len(statements)
        )
        m["  partly supported"] = share(statements.count("partly"), len(statements))
        m["  contradicted or not said"] = share(statements.count("unsupported"), len(statements))
        m["  on nothing the papers discuss"] = share(statements.count("off-topic"), len(statements))
        m["statements with a citation"] = share(len(own), len(statements))
        m["cited statements supported by the paper cited (own check)"] = share(
            own.count("supported"), len(own)
        )
        loose = [x for r in lit for x in r.get("uncited", [])]
        m["sentences citing nothing, per literature answer"] = (
            f"{len(loose) / len(lit):.1f}" if lit else "–"
        )
        m["  borne out by a paper found"] = share(loose.count("supported"), len(loose))
        m["  unsourced"] = share(loose.count("unsourced"), len(loose))
        m["answers saying the papers found do not answer"] = share(
            sum(bool(r.get("abstained")) for r in lit), len(lit)
        )
        m["papers found that help answer (model's judgement)"] = (
            f"{(relevance.count('yes') + 0.5 * relevance.count('partly')) / len(relevance):.2f}"
            f" ({len(relevance)} papers)"
            if relevance
            else "–"
        )
        m["citations giving a page"] = share(pages, cites)
        m["phrases counting studies or giving a verdict"] = str(
            sum(len(r.get("consensus", [])) for r in lit)
        )
    out += ["", "## The literature", ""]
    names = list(next(iter(metrics.values())).keys()) if metrics else []
    out.append(table(["", *systems], [[n, *[metrics[s][n] for s in systems]] for n in names]))
    summary["literature"] = metrics

    # The researcher's data
    rows = []
    for s in systems:
        data = [r for r in by[s] if r["kind"] == "data" and not r["error"]]
        numbers = [n["true"] for r in data for n in r.get("numbers", [])]
        rows.append(
            [
                s,
                share(sum(bool(r["passed"]) for r in data), len(data)),
                share(numbers.count(True), len(numbers)),
                str(numbers.count(False)),
            ]
        )
    out += ["", "## The researcher's data", ""]
    out.append(
        table(["System", "Answers fully right", "Numbers that are true", "Numbers made up"], rows)
    )

    # Time
    rows = []
    for s in systems:
        row = [s]
        for kind in ("research", "data", "chat"):
            t = [r["seconds"] for r in by[s] if r["kind"] == kind and not r["error"]]
            row.append(f"{statistics.median(t):.0f} s" if t else "–")
        words = [r["words"] for r in by[s] if not r["error"]]
        row.append(f"{statistics.median(words):.0f}" if words else "–")
        rows.append(row)
    out += ["", "## Time and length (medians)", ""]
    out.append(table(["System", "Literature", "Data", "Conversation", "Words"], rows))

    # Where the time of a literature answer goes, stage by stage
    stages = ["model", "search", "reading", "checks", "support", "total"]
    rows = []
    for s in systems:
        spent = [
            r.get("timings") or {} for r in by[s] if r["kind"] == "research" and not r["error"]
        ]
        if any(spent):
            rows.append(
                [s]
                + [f"{statistics.median([x.get(st, 0.0) for x in spent]):.1f} s" for st in stages]
            )
    if rows:
        out += ["", "## Where a literature answer's time goes (medians)", ""]
        out.append(table(["System", *stages], rows))

    # Stability: does a system do the same thing each time it is asked?
    rows = []
    for s in systems:
        outcomes = defaultdict(set)
        for r in by[s]:
            if r.get("passed") is not None:
                outcomes[r["case"]].add(r["passed"])
        repeated = [v for v in outcomes.values()]
        rows.append([s, share(sum(len(v) == 1 for v in repeated), len(repeated))])
    out += ["", "## Stability: same outcome on every repeat", ""]
    out.append(table(["System", "Questions"], rows))

    # Every failure, with what was asked and answered
    out += ["", "## Failures", ""]
    for r in scored:
        if r.get("passed") is False or r["error"]:
            failed = [k for k, v in (r.get("checks") or {}).items() if not v]
            answer = (raw[(r["case"], r["system"], r["repeat"])].get("answer") or "").strip()
            out.append(
                f"**{r['case']} · {r['system']} · #{r['repeat']}** — {r['question']}  \n"
                f"Failed: {', '.join(failed) or 'error'}  \n"
                f"> {answer[:600].replace(chr(10), ' ')}{'…' if len(answer) > 600 else ''}\n"
            )
    made_up = [
        (r, x)
        for r in scored
        for x in [*r.get("mentions", []), *r.get("titles", [])]
        if x["found"] is False
    ]
    if made_up:
        out += ["", "## References not found in OpenAlex", ""]
        for r, x in made_up:
            what = x.get("title") or f"{x['name']} ({x['year']})"
            out.append(f"- {r['case']} · {r['system']} · #{r['repeat']}: {what}")
    (folder / "report.md").write_text("\n".join(out) + "\n")
    (folder / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n".join(out[: out.index("## Failures")]))


if __name__ == "__main__":
    main()
