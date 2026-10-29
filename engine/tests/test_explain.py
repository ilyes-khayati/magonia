"""The explanations must reproduce the 2026 paper's (notebook 05, original branch)."""

import json

import pandas as pd
import pytest
from acceptance_cases import DATA
from test_models import PAPERS_MACHINE

from engine.explain import allocation, explain, family, shares, tau


@pytest.fixture(scope="module")
def explained():
    table = pd.read_csv(
        DATA / "reference_features_original.csv", index_col="date", parse_dates=True
    )
    params = json.loads((DATA / "reference_best_params.json").read_text())
    train = table[table["split"] == "train"]
    return explain(train.drop(columns=["target", "split"]), train["target"], params, seeds=5)


def close(name):
    # tree models move a little on other processors (see test_models); Ridge never does
    return 1e-12 if PAPERS_MACHINE or name == "Ridge" else 0.05


def test_reproduces_the_papers_permutation_importance(explained):
    paper = pd.read_csv(DATA / "reference_importance.csv")
    for model, rows in paper.groupby("model"):
        theirs = rows.set_index("feature")["importance"]
        ours = pd.Series(explained.importance[model])[theirs.index]
        if PAPERS_MACHINE or model == "Ridge":
            assert ours.tolist() == pytest.approx(theirs.tolist(), rel=1e-12, abs=1e-12)
        else:
            # a single small input can move by several percent, so compare the shares
            assert (shares(ours) - shares(theirs)).abs().max() < close(model)


def test_reproduces_the_papers_family_shares(explained):
    paper = pd.read_csv(DATA / "reference_family_shares.csv")
    for row in paper.itertuples():
        assert explained.families[row.model][row.family] == pytest.approx(
            row.share, abs=close(row.model)
        )


def test_reproduces_the_papers_agreement(explained):
    paper = pd.read_csv(DATA / "reference_agreement.csv").set_index("pair")
    for pair in explained.agreement:
        row = paper.loc[pair.pair]
        exact = 1e-12 if PAPERS_MACHINE else 0.05
        assert (pair.tau, pair.dist) == pytest.approx((row.tau, row.dist), abs=exact)
        if pair.separable is not None:
            assert pair.separable == bool(row.separable)


def test_families_and_measures():
    assert [
        family(f) for f in ["NDVI_lag1", "LST_lag1", "SPEI_6_lag1", "month_cos", "noise_probe"]
    ] == [
        "own history",
        "LST",
        "drought",
        "calendar",
        "noise probe",
    ]
    a = pd.Series({"x": 3.0, "y": 1.0, "z": -1.0})
    assert shares(a).tolist() == [0.75, 0.25, 0.0]
    assert allocation(a, a) == 0 and tau(a, a) == pytest.approx(1)
    assert allocation(pd.Series({"x": 1.0, "y": 0.0}), pd.Series({"x": 0.0, "y": 1.0})) == 1
