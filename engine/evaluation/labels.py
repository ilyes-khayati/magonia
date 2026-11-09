"""Statements labelled by people: the ruler every automatic judge is measured against.

    uv run python evaluation/labels.py sample RESULTS_DIR [--n 60] [--seed 0]
    uv run python evaluation/labels.py agree RESULTS_DIR

The support check is judged by the same model that wrote the answer, so its verdicts need an
outside reference. `sample` draws statements from a scored run, each with the passages it was
judged against, and writes RESULTS_DIR/labels/sheet.csv. Each person copies it to
sheet-NAME.csv and fills the label column without seeing the automatic verdict, which is kept
apart in key.json.

The draw is stratified by the automatic verdict, so that supported statements, which are the
rarer kind, are not left out: agreement is only meaningful when every label occurs.

`agree` reads every sheet-NAME.csv and writes RESULTS_DIR/labels/agreement.md: how often the
people agree with each other (Cohen's κ for each pair, Fleiss' κ for all), the label most of
them gave, and how well the automatic judge agrees with that label. κ is agreement beyond what
chance alone would give: 0 is chance, 1 is perfect; above 0.6 is usually read as substantial.
"""

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

LABELS = ("supported", "partly", "not supported")
# what people may type in the label column
SHORT = {
    "s": "supported",
    "supported": "supported",
    "yes": "supported",
    "p": "partly",
    "partly": "partly",
    "partial": "partly",
    "n": "not supported",
    "no": "not supported",
    "not": "not supported",
    "not supported": "not supported",
    "unsupported": "not supported",
}
# the automatic judge's verdicts, on the same three labels
JUDGE = {"supported": "supported", "partly": "partly", "unsupported": "not supported"}
FIELDS = ["id", "question", "statement", "passage 1", "passage 2", "label", "note"]

GUIDE = """# Labelling statements

Each row is one sentence an assistant wrote in answer to a question about published research,
with one or two passages from the papers it had found.

Read the statement and the passages, and write in the label column:

- **s**: supported. The passages say what the statement says.
- **p**: partly. The passages say some of it, or say it more weakly, or for another setting.
- **n**: not supported. The passages do not say it, or say the opposite.

Judge only against the passages, not against what you know about the subject. Use the note
column for anything unclear. Save your copy as sheet-YOURNAME.csv in this folder.
"""


def read_statements(folder: Path) -> list[dict]:
    """Every literature statement of a scored run that has passages to be judged against."""
    found = []
    for line in (folder / "scored.jsonl").read_text().splitlines():
        r = json.loads(line)
        for i, s in enumerate(r.get("statements", [])):
            if s.get("pool") in JUDGE and s.get("evidence"):
                found.append(
                    {
                        "case": r["case"],
                        "system": r["system"],
                        "repeat": r["repeat"],
                        "question": r["question"],
                        "n": i,
                        **s,
                    }
                )
    return found


def stratified(statements: list[dict], n: int, seed: int) -> list[dict]:
    """n statements, as evenly as the run allows across the automatic verdicts."""
    rng = random.Random(seed)
    by_verdict: dict[str, list[dict]] = {}
    for s in statements:
        by_verdict.setdefault(s["pool"], []).append(s)
    for group in by_verdict.values():
        rng.shuffle(group)
    chosen: list[dict] = []
    # take one from each verdict in turn, so a rare verdict gets all it has
    while len(chosen) < n and any(by_verdict.values()):
        for verdict in sorted(by_verdict):
            if by_verdict[verdict] and len(chosen) < n:
                chosen.append(by_verdict[verdict].pop())
    rng.shuffle(chosen)  # so the order says nothing about the verdict
    return chosen


def sample(folder: Path, n: int, seed: int) -> Path:
    chosen = stratified(read_statements(folder), n, seed)
    out = folder / "labels"
    out.mkdir(exist_ok=True)
    key = {}
    with (out / "sheet.csv").open("w", newline="") as f:
        sheet = csv.DictWriter(f, FIELDS)
        sheet.writeheader()
        for i, s in enumerate(chosen, 1):
            sid = f"s{i:02d}"
            passages = s["evidence"] + [""] * (2 - len(s["evidence"]))
            sheet.writerow(
                {
                    "id": sid,
                    "question": s["question"],
                    "statement": s["claim"],
                    "passage 1": passages[0],
                    "passage 2": passages[1],
                    "label": "",
                    "note": "",
                }
            )
            key[sid] = {k: s[k] for k in ("case", "system", "repeat", "n", "claim")}
            key[sid]["judge"] = JUDGE[s["pool"]]
    (out / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False))
    (out / "GUIDE.md").write_text(GUIDE)
    return out


def read_sheet(path: Path) -> dict[str, str]:
    """A person's labels by statement id; rows left empty or unreadable are skipped."""
    labels = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            label = SHORT.get((row.get("label") or "").strip().lower())
            if label:
                labels[row["id"]] = label
    return labels


def cohen(a: list[str], b: list[str]) -> float | None:
    """Cohen's κ of two raters over the same items."""
    if not a:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in ca) / len(a) ** 2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def fleiss(items: list[list[str]]) -> float | None:
    """Fleiss' κ of several raters; every item rated by the same number of them."""
    if not items or len(items[0]) < 2:
        return None
    raters = len(items[0])
    counts = [Counter(ratings) for ratings in items]
    p_items = [
        (sum(c * c for c in cnt.values()) - raters) / (raters * (raters - 1)) for cnt in counts
    ]
    observed = sum(p_items) / len(items)
    total = Counter()
    for cnt in counts:
        total.update(cnt)
    expected = sum((v / (len(items) * raters)) ** 2 for v in total.values())
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def majority(ratings: list[str]) -> str | None:
    """The label most people gave; None when there is no single most common one."""
    top = Counter(ratings).most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return None
    return top[0][0]


def binary(labels: list[str]) -> list[str]:
    """Supported or not, for the agreement on the question that matters most."""
    return ["supported" if x == "supported" else "not" for x in labels]


def fmt(k: float | None) -> str:
    return "–" if k is None else f"{k:.2f}"


def agree(folder: Path) -> Path:
    out = folder / "labels"
    key = json.loads((out / "key.json").read_text())
    sheets = {p.stem.removeprefix("sheet-"): read_sheet(p) for p in sorted(out.glob("sheet-*.csv"))}
    people = sorted(sheets)
    # only the statements every person labelled
    ids = sorted(set(key).intersection(*[set(s) for s in sheets.values()])) if sheets else []
    lines = [
        "# Agreement on labelled statements",
        "",
        f"{len(people)} people ({', '.join(people)}), {len(ids)} statements labelled by all of them.",
        "",
        "## Between people",
        "",
        "| Pair | κ, three labels | κ, supported or not |",
        "|---|---|---|",
    ]
    for i, a in enumerate(people):
        for b in people[i + 1 :]:
            la = [sheets[a][x] for x in ids]
            lb = [sheets[b][x] for x in ids]
            lines.append(
                f"| {a} – {b} | {fmt(cohen(la, lb))} | {fmt(cohen(binary(la), binary(lb)))} |"
            )
    ratings = [[sheets[p][x] for p in people] for x in ids]
    lines += ["", f"Fleiss' κ, all people: {fmt(fleiss(ratings))}", ""]

    agreed = {x: m for x, r in zip(ids, ratings) if (m := majority(r))}
    judge = [key[x]["judge"] for x in agreed]
    people_say = list(agreed.values())
    lines += [
        "## The automatic judge against the people",
        "",
        (
            f"{len(agreed)} statements have a majority label "
            f"({len(ids) - len(agreed)} left out, no single most common label)."
        ),
        "",
        f"- κ, three labels: {fmt(cohen(judge, people_say))}",
        f"- κ, supported or not: {fmt(cohen(binary(judge), binary(people_say)))}",
        "",
        "| Judge said ↓ / people said → | " + " | ".join(LABELS) + " |",
        "|---|" + "---|" * len(LABELS),
    ]
    pairs = Counter(zip(judge, people_say))
    for j in LABELS:
        lines.append(f"| {j} | " + " | ".join(str(pairs[(j, h)]) for h in LABELS) + " |")
    systems = Counter(key[x]["system"] for x in ids)
    lines += [
        "",
        "Statements by system: " + ", ".join(f"{s} {n}" for s, n in sorted(systems.items())),
    ]
    path = out / "agreement.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("results", type=Path)
    s.add_argument("--n", type=int, default=60)
    s.add_argument("--seed", type=int, default=0)
    a = sub.add_parser("agree")
    a.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.command == "sample":
        print(sample(args.results, args.n, args.seed))
    else:
        print(agree(args.results))


if __name__ == "__main__":
    main()
