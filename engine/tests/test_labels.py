"""Labelling statements by hand, and the agreement figures computed from the labels."""

import csv
import json
import sys
from pathlib import Path

import pytest
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, str(Path(__file__).parent.parent / "evaluation"))

from labels import agree, cohen, fleiss, majority, read_sheet, sample, stratified


def test_cohen_matches_the_reference_implementation():
    a = [
        "supported",
        "partly",
        "not supported",
        "supported",
        "not supported",
        "partly",
        "supported",
    ]
    b = [
        "supported",
        "not supported",
        "not supported",
        "partly",
        "not supported",
        "partly",
        "supported",
    ]
    assert cohen(a, b) == pytest.approx(cohen_kappa_score(a, b))
    assert cohen(a, a) == 1.0
    assert cohen([], []) is None


def test_fleiss_by_hand():
    # four items, two raters: agreement 0.75, chance 0.53125
    items = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
    assert fleiss(items) == pytest.approx((0.75 - 0.53125) / (1 - 0.53125))
    assert fleiss([["a", "a", "a"], ["b", "b", "b"]]) == 1.0


def test_majority_needs_a_single_most_common_label():
    assert majority(["supported", "supported", "partly"]) == "supported"
    assert majority(["supported", "partly"]) is None


def statement(verdict, i):
    return {"pool": verdict, "claim": f"claim {verdict} {i}", "evidence": ["a passage"]}


def test_the_draw_takes_rare_verdicts_whole_and_hides_the_order():
    statements = [statement("unsupported", i) for i in range(40)]
    statements += [statement("supported", i) for i in range(5)]
    statements += [statement("partly", i) for i in range(20)]
    chosen = stratified(statements, 30, seed=0)
    verdicts = [s["pool"] for s in chosen]
    assert len(chosen) == 30
    assert verdicts.count("supported") == 5  # all the rare ones
    # the rest is shared between the other two, one each in turn
    assert abs(verdicts.count("partly") - verdicts.count("unsupported")) <= 1
    assert stratified(statements, 30, seed=0) == chosen  # the same draw every time


def write_run(folder: Path):
    lines = []
    for case, verdicts in [
        ("r01", ["supported", "unsupported", "partly"]),
        ("r02", ["unsupported", "off-topic"]),
    ]:
        lines.append(
            {
                "case": case,
                "system": "magonia",
                "repeat": 1,
                "question": f"question {case}",
                "statements": [
                    {
                        "claim": f"{case} {v}",
                        "pool": v,
                        "evidence": [] if v == "off-topic" else ["p1", "p2"],
                    }
                    for v in verdicts
                ],
            }
        )
    (folder / "scored.jsonl").write_text("\n".join(json.dumps(x) for x in lines))


def fill(out: Path, name: str, labels: dict[str, str]):
    rows = list(csv.DictReader((out / "sheet.csv").open()))
    for row in rows:
        row["label"] = labels.get(row["id"], "")
    with (out / f"sheet-{name}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def test_a_blind_sheet_then_agreement(tmp_path):
    write_run(tmp_path)
    out = sample(tmp_path, n=10, seed=1)
    rows = list(csv.DictReader((out / "sheet.csv").open()))
    assert len(rows) == 4  # the off-topic statement has no passages to judge
    assert "judge" not in rows[0] and "pool" not in rows[0]  # the sheet does not show the verdict
    key = json.loads((out / "key.json").read_text())
    truth = {
        sid: {"supported": "s", "partly": "p", "not supported": "n"}[k["judge"]]
        for sid, k in key.items()
    }
    fill(out, "anna", truth)
    fill(out, "ben", truth)
    assert read_sheet(out / "sheet-anna.csv") == {
        sid: {"s": "supported", "p": "partly", "n": "not supported"}[v] for sid, v in truth.items()
    }
    report = agree(tmp_path).read_text()
    assert "2 people (anna, ben), 4 statements" in report
    assert "κ, three labels: 1.00" in report
