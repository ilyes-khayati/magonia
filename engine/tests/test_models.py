"""The models must reproduce the research's (notebook 04, original branch, run of November 2026),
given its features and tuned hyperparameters: Ridge, Random Forest, XGBoost and SVR. The
research's MLP is scikit-learn's, not Magonia's network, so it is not compared; SARIMAX is
compared in test_sarimax."""

import json
import platform
import sys

import numpy as np
import pandas as pd
import pytest
from acceptance_cases import DATA

from engine.models import baselines, design, evaluate, features, scores

# results/04_test_scores.csv: RMSE, R2 and MAE on 2022-2024
PAPER = {
    "XGBoost": (0.053580356625794745, 0.8838701158531926, 0.0367883594778754),
    "RandomForest": (0.05834443663862761, 0.8623007120647015, 0.037250461027964255),
    "SVR": (0.05344341157655594, 0.8844629857063486, 0.038931344829089304),
    "Ridge": (0.059658326223408095, 0.8560290328224777, 0.046963707071890286),
}
# results/04_noise_floor.csv: RMSE mean and sd over 20 refits
FLOOR = {
    "XGBoost": (0.05392106149929558, 0.000434323702498876),
    "RandomForest": (0.05843361703507527, 0.00045897294993558314),
    "SVR": (0.05344341157655594, 0.0),
    "Ridge": (0.059658326223408095, 0.0),
}
BASELINES = {"persistence": 0.0971880554489173, "climatology": 0.07509957912791944}
# On the kind of machine the research ran on (Apple silicon) everything is reproduced exactly.
# Elsewhere the tree models' floating-point arithmetic runs in another order, and their
# scores move within the seed noise the research measured; Ridge, SVR and the baselines stay
# exact.
PAPERS_MACHINE = sys.platform == "darwin" and platform.machine() == "arm64"
R2_NOISE = {"XGBoost": 0.0018936855705318518, "RandomForest": 0.0021664869728993106}
EXACT = ("Ridge", "SVR")


def tolerance(name: str, metric: str = "RMSE") -> float:
    if PAPERS_MACHINE or name in EXACT:
        return 1e-12
    return 2 * (R2_NOISE[name] if metric == "R2" else FLOOR[name][1])


@pytest.fixture(scope="module")
def paper_run():
    table = pd.read_csv(DATA / "reference_features_2026-11.csv", index_col="date", parse_dates=True)
    params = json.loads((DATA / "reference_best_params_2026-11.json").read_text())
    X, y = table.drop(columns=["target", "split"]), table["target"]
    return evaluate(X, y, "2022-01-01", params, seeds=20)


def test_reproduces_the_papers_test_scores(paper_run):
    fitted, _ = paper_run
    assert {f.name for f in fitted} == set(PAPER)
    for f in fitted:
        rmse, r2, mae = PAPER[f.name]
        assert f.test["RMSE"] == pytest.approx(rmse, abs=tolerance(f.name))
        assert f.test["R2"] == pytest.approx(r2, abs=tolerance(f.name, "R2"))
        assert f.test["MAE"] == pytest.approx(mae, abs=tolerance(f.name))


def test_reproduces_the_papers_noise_floor(paper_run):
    fitted, _ = paper_run
    for f in fitted:
        mean, sd = FLOOR[f.name]
        assert f.seeds["RMSE_mean"] == pytest.approx(mean, abs=tolerance(f.name))
        # the spread itself is reproduced to within half of it
        assert f.seeds["RMSE_sd"] == pytest.approx(
            sd, abs=1e-12 if PAPERS_MACHINE else sd / 2 + 1e-12
        )


def test_reproduces_the_papers_baselines(paper_run):
    _, base = paper_run
    assert {k: v["RMSE"] for k, v in base.items()} == pytest.approx(BASELINES, abs=1e-12)


def test_features_only_look_back():
    index = pd.date_range("2020-01-01", periods=6, freq="MS")
    y = pd.Series(np.arange(6.0), index=index, name="NDVI")
    X = features(y, [1, 2], {"SPEI-3": (pd.Series(np.arange(6.0) * 10, index=index), [1])})
    assert list(X.columns) == ["NDVI_lag1", "NDVI_lag2", "SPEI-3_lag1", "month_sin", "month_cos"]
    assert X.loc["2020-04-01", ["NDVI_lag1", "NDVI_lag2", "SPEI-3_lag1"]].tolist() == [
        2.0,
        1.0,
        20.0,
    ]


def test_baselines_are_last_month_and_the_usual_month():
    index = pd.date_range("2020-01-01", periods=36, freq="MS")
    y = pd.Series(np.tile(np.arange(12.0), 3), index=index)
    train = pd.Series(index < "2022-01-01", index=index)
    b = baselines(y, train)
    assert scores(y[~train], b["climatology"][~train])["RMSE"] == 0
    assert b["persistence"]["2022-03-01"] == 1.0


def test_a_forecast_recommends_its_predictors_and_says_what_it_found():
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    found = forecast(
        "Orchard", ("NDVI", "ndvi", d.NDVI), [("SPEI-6", "spei", d.SPEI_6)], seeds=2, draws=2
    )
    names = [f["name"] for f in found.features]
    assert names[0] == "NDVI lag 1" and names[-1] == "calendar month"
    assert all(f["reason"] for f in found.features)
    assert found.test == ("2022-01", "2024-12") and len(found.observed) == 36
    assert found.summary[0].startswith(
        "Orchard: NDVI one month ahead, trained on 2002-03 to 2021-12"
    )
    assert "persistence 0.0972, climatology 0.0753" in found.summary[1]
    assert {m.name for m in found.models} == {"Ridge", "RandomForest", "XGBoost"}


def test_lags_chosen_by_the_researcher_are_used_as_given():
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    found = forecast(
        "Orchard",
        ("NDVI", "ndvi", d.NDVI),
        [("LST", "lst", d.LST)],
        [1, 2],
        {"lst": [3]},
        seeds=1,
        draws=1,
    )
    assert [f["name"] for f in found.features] == [
        "NDVI lag 1",
        "NDVI lag 2",
        "LST lag 3",
        "calendar month",
    ]


def test_too_short_a_series_is_refused():
    from engine.models import ForecastError, forecast

    index = pd.date_range("2018-01-01", periods=60, freq="MS")
    y = pd.Series(np.sin(np.arange(60) / 2), index=index)
    with pytest.raises(ForecastError, match="8 years to train"):
        forecast("Field", ("NDVI", "ndvi", y), [], [1])


def test_gaps_leave_baselines_scored_where_they_exist():
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    snowy = d.NDVI.where(~d.index.month.isin([1, 2]))  # winters missing, as under snow
    found = forecast("Field", ("NDVI", "ndvi", snowy), [], [1], seeds=1, draws=1)
    assert found.baselines["persistence"]["months"] < len(found.observed)
    assert "persistence" in found.summary[1] and "months)" in found.summary[1]


def test_the_researcher_chooses_the_models_their_settings_and_the_predictors():
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    found = forecast(
        "Orchard",
        ("NDVI", "ndvi", d.NDVI),
        [],
        [1, 12],
        seeds=2,
        models=["XGBoost", "Ridge"],
        params={"Ridge": {"alpha": 2.5}, "XGBoost": {"n_estimators": 50, "max_depth": 3}},
        calendar=False,
        rolling=False,
    )
    assert [m.name for m in found.models] == ["Ridge", "XGBoost"]  # in the usual order
    assert found.models[0].params == {"ridge__alpha": 2.5}
    assert found.models[1].params == {"n_estimators": 50, "max_depth": 3}
    assert [f["name"] for f in found.features] == ["NDVI lag 1", "NDVI lag 12"]
    assert all(not m.rolling or len(m.rolling) == 1 for m in found.models)
    assert not any("test windows" in line for line in found.summary)


def test_one_model_alone_is_reported_without_a_ranking():
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    found = forecast("Orchard", ("NDVI", "ndvi", d.NDVI), [], [1], models=["Ridge"], rolling=False)
    assert "lowest test error Ridge (RMSE" in found.summary[1] and ", then" not in found.summary[1]
    assert not any("seeds" in line for line in found.summary)
    assert (
        found.summary[-1].startswith("Orchard: Ridge beats both baselines")
        or "does not" in (found.summary[-1])
    )


@pytest.mark.parametrize(
    ("choice", "message"),
    [
        ({"models": []}, "at least one model"),
        ({"params": {"Ridge": {"depth": 3}}, "models": ["Ridge"]}, "no setting 'depth'"),
        ({"params": {"XGBoost": {"learning_rate": 5}}, "models": ["XGBoost"]}, "between"),
        ({"calendar": False, "own_lags": []}, "at least one predictor"),
    ],
)
def test_impossible_choices_are_refused_with_a_reason(choice, message):
    from engine.models import ForecastError, forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    own = choice.pop("own_lags", [1])
    with pytest.raises(ForecastError, match=message):
        forecast("Orchard", ("NDVI", "ndvi", d.NDVI), [], own, seeds=1, draws=1, **choice)


def test_lags_are_recommended_on_the_training_years_only():
    # a driver linked to the response only in the test years must not be chosen: the lags
    # were chosen on the whole record until 18 Nov, and this one then "stood out"
    rng = np.random.default_rng(1)
    months = pd.date_range("2005-01-01", periods=240, freq="MS")
    y = pd.Series(rng.normal(size=240), months)
    x = pd.Series(rng.normal(size=240), months)
    x.iloc[-61:-1] = -y.iloc[-60:].to_numpy()
    _, _, chosen, test_start = design(
        ("NDVI", "ndvi", y), [("LST", "lst", x)], own_lags=[1], test_years=5, calendar=False
    )
    assert test_start == "2020-01-01"
    assert [c["name"] for c in chosen if c["name"].startswith("LST")] == ["LST"]  # left out


def test_svr_is_offered_as_in_the_research_and_fits_the_same_every_time():
    from engine.explain import explain
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    found = forecast(
        "Orchard",
        ("NDVI", "ndvi", d.NDVI),
        [],
        [1, 12],
        seeds=3,
        models=["SVR", "Ridge"],
        params={"SVR": {"C": 10, "gamma": 0.1, "epsilon": 0.05}},
        rolling=False,
    )
    svr = next(m for m in found.models if m.name == "SVR")
    assert svr.params == {
        "regressor__svr__C": 10.0,
        "regressor__svr__gamma": 0.1,
        "regressor__svr__epsilon": 0.05,
    }
    assert svr.seeds["runs"] == 1  # no randomness: one fit says it all
    assert svr.test["R2"] > 0.5

    table = pd.read_csv(DATA / "reference_features_2026-11.csv", index_col="date", parse_dates=True)
    train = table[table["split"] == "train"].iloc[:120]
    X, y = train.drop(columns=["target", "split"]), train["target"]
    explained = explain(X, y, {"SVR": {"regressor__svr__C": 10.0}}, seeds=2)
    assert "SVR" in explained.families  # explained by shuffling
    assert "SVR" not in explained.native  # it has no importance of its own


def test_sarimax_is_scored_like_the_other_models_and_says_its_orders():
    from engine.models import forecast

    d = pd.read_csv(
        DATA / "reference_decomposition.csv", index_col="date", parse_dates=True
    ).asfreq("MS")
    found = forecast(
        "Orchard",
        ("NDVI", "ndvi", d.NDVI),
        [],
        [1, 12],
        seeds=2,
        models=["SARIMAX", "Ridge"],
        params={"Ridge": {"alpha": 1.0}},
        rolling=False,
    )
    sarimax = next(m for m in found.models if m.name == "SARIMAX")
    assert len(sarimax.predictions) == len(found.dates)
    assert sarimax.seeds["runs"] == 1 and sarimax.test["R2"] > 0.5
    assert set(sarimax.params) == {"order", "seasonal_order", "trend"}
    assert any("SARIMAX(" in line and "research's rule" in line for line in found.summary)


def test_the_research_design_orders_the_columns_and_adds_its_noise_probe():
    from engine.models import design

    months = pd.date_range("2000-03-01", periods=120, freq="MS")
    rng = np.random.default_rng(1)
    y = pd.Series(rng.normal(size=120), index=months)
    spei = pd.Series(rng.normal(size=120), index=months)
    lst = pd.Series(rng.normal(size=120), index=months)
    X, _, chosen, _ = design(
        ("NDVI", "ndvi", y),
        [("SPEI_6", "spei", spei), ("LST", "lst", lst)],
        [1, 12],
        {"spei": [2], "lst": [1]},
        test_years=2,
        research=True,
    )
    assert list(X.columns) == [
        "NDVI_lag1",
        "NDVI_lag12",
        "month_cos",
        "month_sin",
        "SPEI_6_lag2",
        "LST_lag1",
        "noise_probe",
    ]
    # as notebook 03: seed 0 over the months where the response and every driver exist
    noise = pd.Series(np.random.default_rng(0).standard_normal(120), index=months)
    assert np.allclose(X["noise_probe"], noise.reindex(X.index))
    assert chosen[-1]["name"] == "noise probe"
