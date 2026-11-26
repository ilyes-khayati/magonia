"""SARIMAX must reproduce the research's (notebook 04, original branch, run of November 2026),
given its features: the orders its rule chooses, the residual check and the test scores."""

import pandas as pd
import pytest
from acceptance_cases import DATA

from engine.models import scores
from engine.sarimax import reference, regressors


@pytest.fixture(scope="module")
def found():
    table = pd.read_csv(DATA / "reference_features_2026-11.csv", index_col="date", parse_dates=True)
    X = table.drop(columns=["target", "split", "noise_probe"])
    y = table["target"].rename("NDVI")
    test = table.index[table["split"] == "test"]
    return reference(X, y, f"{test[0]:%Y-%m-%d}"), y[test]


def test_reproduces_the_orders_the_research_rule_chose(found):
    r, _ = found
    assert (r.spec.order, r.spec.seasonal_order, r.spec.trend) == ((2, 0, 0), (1, 1, 1, 12), "n")
    assert r.ljung_box["12"] == pytest.approx(0.829331231025172, abs=1e-6)


def test_reproduces_the_research_test_scores(found):
    r, observed = found
    s = scores(observed, r.predictions.reindex(observed.index))
    # results/04_test_scores.csv
    assert s["RMSE"] == pytest.approx(0.054099912278087185, rel=1e-6)
    assert s["R2"] == pytest.approx(0.8816070301641854, rel=1e-6)


def test_only_the_drivers_are_regressors(found):
    r, _ = found
    assert [c["term"] for c in r.coefficients] == ["SPEI_6_lag2", "LST_lag1"]
    lst = r.coefficients[1]
    assert lst["value"] < 0 and lst["p"] < 0.01  # warmer last month, lower NDVI
    columns = ["NDVI_lag1", "NDVI_lag12", "LST_lag1", "month_sin", "month_cos"]
    assert regressors(pd.DataFrame(columns=columns), "NDVI") == ["LST_lag1"]
