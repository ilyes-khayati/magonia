"""The lag evidence must reproduce the 2026 paper's (notebook 03, stage 2, original branch)."""

import numpy as np
import pandas as pd
import pytest
from acceptance_cases import DATA

from engine.lags import acf, bound, deseasonalise, driver_evidence, effective_n

TRAIN_END = "2021-12-01"
# the own-history predictors the paper's lasso kept for the original NDVI
OWN = [1, 3, 11, 12, 14, 18, 23, 24]
# its printed table: strongest lag, r and bound for each climate variable
PAPER = {
    "LST": (2, -0.059, 0.227, "not significant"),
    "SPEI_1": (12, -0.173, 0.190, "not significant"),
    "SPEI_3": (1, 0.185, 0.214, "not significant"),
    "SPEI_6": (1, 0.247, 0.224, "stands out"),
    "SPEI_12": (9, -0.114, 0.231, "not significant"),
    "SPEI_24": (12, -0.163, 0.233, "not significant"),
    "SPEI_48": (10, -0.181, 0.234, "not significant"),
}


@pytest.fixture(scope="module")
def train():
    d = pd.read_csv(DATA / "reference_decomposition.csv", index_col="date", parse_dates=True)
    return d[d.index <= TRAIN_END]


def residual(train):
    """What NDVI's own history does not explain: the paper's stage-1 regression."""
    y = train["NDVI"]
    X = pd.DataFrame({f"lag{k}": y.shift(k) for k in OWN})
    X["month_cos"] = np.cos(2 * np.pi * train.index.month / 12)
    D = pd.concat([y.rename("y"), X], axis=1).dropna()
    A = np.column_stack([np.ones(len(D)), D[X.columns]])
    coef, *_ = np.linalg.lstsq(A, D["y"], rcond=None)
    return pd.Series(D["y"].to_numpy() - A @ coef, index=D.index)


@pytest.mark.parametrize("column", PAPER)
def test_reproduces_the_papers_climate_evidence(train, column):
    lag, r, limit, decision = PAPER[column]
    key = "lst" if column == "LST" else "spei"
    found = driver_evidence(residual(train), train[column], column, key)
    assert (found.lag, round(found.best, 3), round(found.bound, 3), found.decision) == (
        lag,
        r,
        limit,
        decision,
    )


def test_the_bound_shrinks_the_sample_for_smooth_series():
    assert effective_n(100, 0.0, 0.9) == 100
    assert effective_n(100, 0.9, 0.9) == pytest.approx(10.5, abs=0.1)
    rng = np.random.default_rng(1)
    index = pd.date_range("2000-01-01", periods=240, freq="MS")
    noise = pd.Series(rng.normal(size=240), index=index)
    smooth = noise.rolling(6, min_periods=1).mean()
    assert bound(smooth, smooth) > 1.5 * bound(noise, noise)


def test_a_lagged_driver_with_the_wrong_sign_is_not_a_finding():
    rng = np.random.default_rng(2)
    index = pd.date_range("2000-01-01", periods=240, freq="MS")
    heat = pd.Series(rng.normal(size=240), index=index)
    green = heat.shift(3) * 0.8 + pd.Series(rng.normal(0, 0.5, 240), index=index)
    assert driver_evidence(green, heat, "LST", "spei").decision == "stands out"
    found = driver_evidence(green, heat, "LST", "lst")
    assert (found.lag, found.decision) == (3, "implausible sign")


def test_autocorrelation_and_deseasonalising():
    index = pd.date_range("2000-01-01", periods=120, freq="MS")
    cycle = pd.Series(np.sin(np.arange(120) * 2 * np.pi / 12), index=index)
    assert acf(cycle)[11] == pytest.approx(0.9, abs=0.01)  # a yearly cycle remembers itself at 12
    assert deseasonalise(cycle).abs().max() < 1e-9


def test_the_explorer_describes_memory_and_each_driver(train):
    from engine.lags import explore

    found = explore(
        "Orchard", ("NDVI", "ndvi", train["NDVI"]), [("SPEI-6", "spei", train["SPEI_6"])]
    )
    assert found.summary[0].startswith("Orchard: NDVI anomalies remember themselves at")
    assert found.drivers[0].decision in ("stands out", "not significant", "implausible sign")
    assert found.summary[1].startswith("Orchard: SPEI-6 ")
    assert len(found.acf) == 24 and len(found.drivers[0].r) == 12


def test_empty_winter_months_do_not_join_the_months_around_them():
    rng = np.random.default_rng(3)
    x = [0.0]
    for _ in range(359):
        x.append(0.8 * x[-1] + rng.normal())
    series = pd.Series(x, index=pd.date_range("1990-01-01", periods=360, freq="MS"))
    snowy = series.where(~series.index.month.isin([12, 1, 2]))
    assert acf(snowy)[0] == pytest.approx(acf(series)[0], abs=0.1)
    assert acf(snowy)[0] > 0.6
