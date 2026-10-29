"""The models must reproduce the 2026 paper's (notebook 04, original branch), given its
features and tuned hyperparameters."""

import json
import platform
import sys

import numpy as np
import pandas as pd
import pytest
from acceptance_cases import DATA

from engine.models import baselines, evaluate, features, scores

# notebook 04: test scores, then the seed noise floor (RMSE mean and sd over 20 refits)
PAPER = {
    "XGBoost": (0.055026274040545574, 0.8775921501910211, 0.03676687011105039),
    "RandomForest": (0.058445431325578244, 0.8619074682237751, 0.038482721103566646),
    "Ridge": (0.0584405287012065, 0.8619306347023572, 0.045603599036797116),
}
FLOOR = {
    "XGBoost": (0.05496766466301343, 0.0005192189968367159),
    "RandomForest": (0.05814177783391047, 0.0004175191230628132),
    "Ridge": (0.0584405287012065, 0.0),
}
BASELINES = {"persistence": 0.09719612395317319, "climatology": 0.07525357245463063}
# On the kind of machine the paper ran on (Apple silicon) everything is reproduced exactly.
# Elsewhere the tree models' floating-point arithmetic runs in another order, and their
# scores move within the seed noise the paper measured; Ridge and the baselines stay exact.
PAPERS_MACHINE = sys.platform == "darwin" and platform.machine() == "arm64"
R2_NOISE = {"XGBoost": 0.0023164620614287905, "RandomForest": 0.001965913457553337}


def tolerance(name: str, metric: str = "RMSE") -> float:
    if PAPERS_MACHINE or name == "Ridge":
        return 1e-12
    return 2 * (R2_NOISE[name] if metric == "R2" else FLOOR[name][1])


FIRST_WINDOW = {
    "XGBoost": 0.05378960826894959,
    "RandomForest": 0.056193956668892715,
    "Ridge": 0.057588784611628994,
}


@pytest.fixture(scope="module")
def paper_run():
    table = pd.read_csv(
        DATA / "reference_features_original.csv", index_col="date", parse_dates=True
    )
    params = json.loads((DATA / "reference_best_params.json").read_text())
    X, y = table.drop(columns=["target", "split"]), table["target"]
    return evaluate(X, y, "2022-01-01", params, seeds=20, windows=[("2010-01-01", "2012-12-01")])


def test_reproduces_the_papers_test_scores(paper_run):
    fitted, _ = paper_run
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


def test_reproduces_the_papers_baselines_and_a_rolling_window(paper_run):
    fitted, base = paper_run
    assert {k: v["RMSE"] for k, v in base.items()} == pytest.approx(BASELINES, abs=1e-12)
    for f in fitted:
        assert f.rolling[0]["RMSE"] == pytest.approx(FIRST_WINDOW[f.name], abs=tolerance(f.name))


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
