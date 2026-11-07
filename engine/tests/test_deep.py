import numpy as np
import pandas as pd

from engine.deep import DeepRegressor, layout
from engine.explain import explain
from engine.models import features


def seasonal(n=180, seed=0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2005-01-01", periods=n, freq="MS")
    t = np.arange(n)
    y = pd.Series(
        0.5 + 0.2 * np.sin(2 * np.pi * t / 12) + 0.02 * rng.normal(size=n), index, name="NDVI"
    )
    heat = pd.Series(25 - 8 * np.sin(2 * np.pi * (t - 1) / 12) + rng.normal(size=n), index)
    X = features(y, [1, 2, 12], {"LST": (heat, [1, 2])})
    ok = X.notna().all(axis=1)
    return X[ok], y[ok]


def test_lag_columns_become_a_sequence_and_the_calendar_stays_aside():
    series, longest, cells, statics = layout(["NDVI_lag1", "NDVI_lag12", "LST_lag2", "month_sin"])
    assert series == ["NDVI", "LST"] and longest == 12
    assert (0, 0, 11) in cells and (1, 0, 0) in cells and (2, 1, 10) in cells
    assert statics == [3]


def test_each_network_learns_a_seasonal_series_and_refits_the_same():
    X, y = seasonal()
    train = X.index < "2016-01-01"
    for kind in ("mlp", "lstm", "gru", "cnn"):
        model = DeepRegressor(kind=kind, epochs=300).fit(X[train], y[train])
        error = np.sqrt(np.mean((model.predict(X[~train]) - y[~train]) ** 2))
        assert error < 0.06, kind  # the cycle's amplitude is 0.2
        again = DeepRegressor(kind=kind, epochs=300).fit(X[train], y[train])
        np.testing.assert_allclose(model.predict(X[~train]), again.predict(X[~train]), atol=1e-6)


def test_a_networks_gradients_point_to_what_it_uses():
    X, y = seasonal()
    model = DeepRegressor(kind="gru", epochs=300).fit(X, y)
    push = np.abs(model.gradients(X)).mean(axis=0)
    assert push.shape == (X.shape[1],)
    assert X.columns[np.argmax(push)] in (
        "NDVI_lag12",
        "NDVI_lag1",
        "LST_lag1",
        "month_sin",
        "month_cos",
    )


def test_explanations_give_each_models_own_method_and_a_monthly_account():
    X, y = seasonal(n=150)
    found = explain(X, y, {"Ridge": {}, "MLP": {"epochs": 150}}, seeds=2)
    assert found.native["Ridge"]["method"] == "standardised coefficients"
    assert found.native["MLP"]["method"] == "gradient × input"
    assert -1 <= found.native["MLP"]["tau"] <= 1
    first = found.timeline["Ridge"][0]
    assert first["date"] == f"{X.index[0]:%Y-%m}" and "own history" in first
