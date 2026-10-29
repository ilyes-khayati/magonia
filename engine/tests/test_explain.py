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


def test_comparisons_between_models_are_written_by_code():
    from engine.explain import Explanation, Pair, describe

    found = Explanation(
        importance={
            "XGBoost": {"LST_lag1": 0.6, "NDVI_lag1": 0.3},
            "Ridge": {"LST_lag1": 0.2, "NDVI_lag1": 0.7},
        },
        families={
            "XGBoost": {"LST": 0.62, "own history": 0.29, "calendar": 0.09},
            "Ridge": {"LST": 0.19, "own history": 0.70, "calendar": 0.11},
        },
        agreement=[
            Pair("XGBoost vs itself", 0.97, 0.96, 0.99, 0.02, 0.01, 0.03),
            Pair("Ridge vs itself", 0.98, 0.97, 0.99, 0.01, 0.0, 0.02),
            Pair("XGBoost vs Ridge", 0.54, 0.5, 0.6, 0.40, 0.38, 0.42, True),
        ],
        seeds=5,
    )
    lines = describe("Orchard", found)
    assert "Orchard: of the models, XGBoost leans most on LST (62%) and Ridge least (19%)." in lines
    assert (
        "Orchard: of the models, Ridge leans most on own history (70%) and XGBoost least (29%)."
        in lines
    )
    assert (
        "Orchard: of the models, Ridge leans most on calendar (11%) and XGBoost least (9%)."
        in lines
    )
    assert any(
        line.startswith("Orchard: XGBoost and Ridge explain the data differently") for line in lines
    )


def test_stability_says_which_models_keep_their_story_across_training_windows():
    import numpy as np

    from engine.explain import stability

    index = pd.date_range("2000-01-01", periods=12 * 16, freq="MS")
    rng = np.random.default_rng(0)
    own = pd.Series(rng.normal(size=len(index)), index)
    X = pd.DataFrame({"NDVI_lag1": own, "LST_lag1": rng.normal(size=len(index))}, index=index)
    y = 2 * own + 0.1 * rng.normal(size=len(index))  # only its own past matters
    params = {"Ridge": {"ridge__alpha": 1.0}}
    found = stability("Orchard", X, y, params, "2013-01-01", windows=3, seeds=1)
    assert [w["train_end"] for w in found.windows] == ["2010-12", "2011-12", "2012-12"]
    assert found.leading == {"Ridge": ["own history"] * 3}
    assert found.summary[0].startswith(
        "Orchard: across 3 training windows ending 2010-12 to 2012-12, Ridge always leans most on own history"
    )
    short = stability("Orchard", X, y, params, "2008-06-01", windows=3, seeds=1)
    assert "stability cannot be checked" in short.summary[0]
