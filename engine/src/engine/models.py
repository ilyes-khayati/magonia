"""Forecasting a monthly series one month ahead from its own past and its drivers' past.

The method of the 2026 paper (notebook 04). Ridge, Random Forest and XGBoost are tuned on the
training years only, by search over a time-series split, and scored once on the most recent
years, never on a random split. Two baselines say whether a model learned anything:
persistence (last month's value) and climatology (the training average of the calendar
month). Refitting the tree models with different seeds measures how much a score moves by
chance alone, and a rolling origin repeats the test over several earlier windows.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import loguniform, randint, uniform
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from engine.lags import acf, deseasonalise, driver_evidence

SEED = 0
NAMES = ("Ridge", "RandomForest", "XGBoost")

# the paper's estimators and search spaces
ESTIMATORS = {
    "XGBoost": XGBRegressor(random_state=SEED, n_jobs=1),
    "RandomForest": RandomForestRegressor(random_state=SEED, n_jobs=1),
    "Ridge": make_pipeline(StandardScaler(), Ridge()),
}
SPACES = {
    "XGBoost": {
        "n_estimators": randint(200, 800),
        "max_depth": randint(2, 7),
        "learning_rate": loguniform(0.01, 0.2),
        "subsample": uniform(0.6, 0.4),
        "colsample_bytree": uniform(0.6, 0.4),
        "min_child_weight": randint(1, 11),
    },
    "RandomForest": {
        "n_estimators": randint(300, 800),
        "max_depth": [None, 4, 6, 8, 12],
        "min_samples_leaf": randint(1, 11),
        "max_features": ["sqrt", 0.5, 1.0],
    },
    "Ridge": {"ridge__alpha": np.logspace(-4, 3, 50)},
}


def features(
    target: pd.Series,
    own_lags: list[int],
    drivers: dict[str, tuple[pd.Series, list[int]]],
    calendar: bool = True,
) -> pd.DataFrame:
    """Predictors known before each month: the target's and the drivers' earlier values,
    and the calendar month as a cycle."""
    X = pd.DataFrame(index=target.index)
    for k in own_lags:
        X[f"{target.name}_lag{k}"] = target.shift(k)
    for name, (series, lags) in drivers.items():
        for k in lags:
            X[f"{name}_lag{k}"] = series.reindex(target.index).shift(k)
    if calendar:
        month = target.index.month
        X["month_sin"] = np.sin(2 * np.pi * month / 12)
        X["month_cos"] = np.cos(2 * np.pi * month / 12)
    return X


def estimator(name: str, params: dict, seed: int = SEED):
    model = clone(ESTIMATORS[name]).set_params(**params)
    if name != "Ridge":
        model.set_params(random_state=seed)
    return model


def tune(name: str, X: pd.DataFrame, y: pd.Series, draws: int = 40) -> dict:
    """Hyperparameters chosen on the training years only, by RMSE over a time-series split."""
    cv = TimeSeriesSplit(n_splits=5)
    if name == "Ridge":
        search = GridSearchCV(
            ESTIMATORS[name], SPACES[name], cv=cv, scoring="neg_mean_squared_error", n_jobs=-1
        )
    else:
        search = RandomizedSearchCV(
            ESTIMATORS[name],
            SPACES[name],
            n_iter=draws,
            cv=cv,
            scoring="neg_mean_squared_error",
            random_state=SEED,
            n_jobs=-1,
        )
    params = search.fit(X, y).best_params_
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in params.items()}


def scores(y: pd.Series, p) -> dict:
    return {
        "RMSE": float(np.sqrt(mean_squared_error(y, p))),
        "R2": float(r2_score(y, p)),
        "MAE": float(mean_absolute_error(y, p)),
    }


def baselines(y: pd.Series, train: pd.Series) -> dict[str, pd.Series]:
    """Last month's value, and the training average of the calendar month."""
    normal = y[train].groupby(y[train].index.month).mean()
    return {
        # the value of the calendar month before, which may be missing after a gap
        "persistence": y.shift(1, freq="MS").reindex(y.index),
        "climatology": pd.Series(y.index.month.map(normal), index=y.index),
    }


@dataclass
class Fitted:
    name: str
    params: dict
    test: dict  # RMSE, R2 and MAE on the test years, seed 0
    seeds: dict = field(default_factory=dict)  # mean and sd of RMSE and R2 over refits
    rolling: list[dict] = field(default_factory=list)  # one score per earlier window
    predictions: list[float] = field(default_factory=list)


def evaluate(
    X: pd.DataFrame,
    y: pd.Series,
    test_start: str,
    params: dict[str, dict],
    seeds: int = 20,
    windows: list[tuple[str, str]] | None = None,
) -> tuple[list[Fitted], dict[str, dict]]:
    """Fit each model on the years before test_start and score it on the years from it; the
    baselines are scored on the same months."""
    train, test = X.index < test_start, X.index >= test_start
    fitted = []
    for name in NAMES:
        model = estimator(name, params[name]).fit(X[train], y[train])
        p = model.predict(X[test])
        f = Fitted(name, params[name], scores(y[test], p), predictions=[float(v) for v in p])
        runs = [
            scores(
                y[test], estimator(name, params[name], s).fit(X[train], y[train]).predict(X[test])
            )
            for s in (range(seeds) if name != "Ridge" else [SEED])
        ]
        f.seeds = {
            "runs": len(runs),
            "RMSE_mean": float(np.mean([r["RMSE"] for r in runs])),
            "RMSE_sd": float(np.std([r["RMSE"] for r in runs])),
            "R2_mean": float(np.mean([r["R2"] for r in runs])),
            "R2_sd": float(np.std([r["R2"] for r in runs])),
        }
        for start, end in windows or []:
            before, inside = X.index < start, (X.index >= start) & (X.index <= end)
            p = estimator(name, params[name]).fit(X[before], y[before]).predict(X[inside])
            f.rolling.append({"window": f"{start[:4]}-{end[:4]}", **scores(y[inside], p)})
        fitted.append(f)
    # a baseline is scored where it exists: after a gap there is no "last month"
    base = {}
    for name, s in baselines(y, pd.Series(train, index=y.index)).items():
        ok = s[test].notna()
        base[name] = {**scores(y[test][ok], s[test][ok]), "months": int(ok.sum())}
    return fitted, base


LABELS = {"Ridge": "Ridge", "RandomForest": "Random Forest", "XGBoost": "XGBoost"}
MIN_TRAIN_YEARS = 8


def recommend_own_lags(y: pd.Series, most: int = 4) -> tuple[list[int], str]:
    """Lag 1, a year earlier if it stands out, and the next strongest lags beyond chance."""
    memory = acf(y)
    band = 1.96 / np.sqrt(y.notna().sum())
    standing = [k + 1 for k, r in enumerate(memory) if abs(r) > band]
    chosen = [1] + ([12] if 12 in standing else [])
    for k in sorted(standing, key=lambda k: -abs(memory[k - 1])):
        if len(chosen) >= most:
            break
        if k not in chosen:
            chosen.append(k)
    return sorted(chosen), f"autocorrelation beyond chance (±{band:.2f}), strongest first"


def recommend_driver_lag(
    y: pd.Series, x: pd.Series, title: str, key: str
) -> tuple[int | None, str]:
    """The driver's strongest lag if it stands out in the lag explorer's test."""
    found = driver_evidence(deseasonalise(y), deseasonalise(x), title, key)
    reason = f"lag {found.lag}: r = {found.best:.2f}, bound ±{found.bound:.2f}, {found.decision}"
    return (found.lag if found.decision == "stands out" else None), reason


@dataclass
class Forecast:
    features: list[dict]  # name and why it is there
    train: tuple[str, str]
    test: tuple[str, str]
    dates: list[str]  # the test months
    observed: list[float]
    models: list[Fitted]
    baselines: dict[str, dict]
    summary: list[str]

    def to_dict(self) -> dict:
        return {
            "features": self.features,
            "train": list(self.train),
            "test": list(self.test),
            "dates": self.dates,
            "observed": self.observed,
            "models": [
                {
                    k: getattr(m, k)
                    for k in ("name", "params", "test", "seeds", "rolling", "predictions")
                }
                for m in self.models
            ],
            "baselines": self.baselines,
            "summary": self.summary,
        }


class ForecastError(ValueError):
    """The series is too short or too gappy to train and test a model."""


def design(
    target: tuple[str, str, pd.Series],
    drivers: list[tuple[str, str, pd.Series]],
    own_lags: list[int] | None = None,
    driver_lags: dict[str, list[int]] | None = None,
    test_years: int = 3,
) -> tuple[pd.DataFrame, pd.Series, list[dict], str]:
    """The predictors, the target, why each predictor is there, and the first test month."""
    title, _, y = target
    y = y.rename(title)
    chosen = []
    if own_lags is None:
        own_lags, why = recommend_own_lags(y)
    else:
        why = "chosen by the researcher"
    chosen += [{"name": f"{title} lag {k}", "reason": why} for k in own_lags]
    lagged = {}
    for name, dkey, x in drivers:
        if driver_lags is not None and dkey in driver_lags:
            lags, why = driver_lags[dkey], "chosen by the researcher"
        else:
            best, why = recommend_driver_lag(y, x, name, dkey)
            lags = [best] if best else []
            if not lags:
                chosen.append({"name": f"{name}", "reason": f"left out: {why}"})
        if lags:
            lagged[name] = (x, lags)
            chosen += [{"name": f"{name} lag {k}", "reason": why} for k in lags]
    chosen.append({"name": "calendar month", "reason": "the seasonal cycle, as sine and cosine"})

    X = features(y, own_lags, lagged)
    table = pd.concat([X, y.rename("target")], axis=1).dropna()
    X, y = table.drop(columns="target"), table["target"]
    end = y.index.max()
    test_start = (end - pd.DateOffset(years=test_years) + pd.DateOffset(months=1)).strftime(
        "%Y-%m-01"
    )
    return X, y, chosen, test_start


def forecast(
    area: str,
    target: tuple[str, str, pd.Series],
    drivers: list[tuple[str, str, pd.Series]],
    own_lags: list[int] | None = None,
    driver_lags: dict[str, list[int]] | None = None,
    test_years: int = 3,
    seeds: int = 20,
    draws: int = 12,
) -> Forecast:
    """Forecast a monthly target one month ahead; lags not given are recommended by code."""
    title, key, _ = target
    X, y_, chosen, test_start = design(target, drivers, own_lags, driver_lags, test_years)
    end = y_.index.max()
    train = X.index < test_start
    if train.sum() < 12 * MIN_TRAIN_YEARS or (~train).sum() < 12:
        raise ForecastError(
            f"A forecast needs {MIN_TRAIN_YEARS} years to train and {test_years} to test, without "
            "gaps in the predictors; choose a longer period."
        )
    params = {name: tune(name, X[train], y_[train], draws) for name in NAMES}

    # earlier test windows of the same length, back while enough years remain to train on
    windows, start = [], pd.Timestamp(test_start)
    while True:
        window_end = start + pd.DateOffset(years=test_years) - pd.DateOffset(months=1)
        windows.insert(0, (start.strftime("%Y-%m-01"), min(window_end, end).strftime("%Y-%m-01")))
        start -= pd.DateOffset(years=test_years)
        if (X.index < start).sum() < 12 * MIN_TRAIN_YEARS or len(windows) == 5:
            break
    fitted, base = evaluate(X, y_, test_start, params, seeds, windows)

    digits = 2 if key == "lst" else 4

    def fmt(v: float) -> str:
        return f"{v:.{digits}f}"

    order = sorted(fitted, key=lambda f: f.test["RMSE"])
    first, last = X.index[train][0], X.index[train][-1]
    n_test = int((~train).sum())
    span = (
        f"{area}: {title} one month ahead, trained on {first:%Y-%m} to {last:%Y-%m} and tested "
        f"on {test_start[:7]} to {end:%Y-%m} ({int((~train).sum())} months)."
    )
    ranking = (
        f"{area}: lowest test error {LABELS[order[0].name]} (RMSE {fmt(order[0].test['RMSE'])}, "
        f"R² {order[0].test['R2']:.2f}), then "
        + ", ".join(f"{LABELS[f.name]} {fmt(f.test['RMSE'])}" for f in order[1:])
        + "; "
        + ", ".join(
            f"{b} {fmt(base[b]['RMSE'])}"
            + (
                f" (on {base[b]['months']} of {n_test} months)"
                if base[b]["months"] < n_test
                else ""
            )
            for b in ("persistence", "climatology")
        )
        + "."
    )
    summary = [span, ranking]
    floor = max(f.seeds["RMSE_sd"] for f in fitted)
    gap = order[1].test["RMSE"] - order[0].test["RMSE"]
    within = "within" if gap <= 2 * floor else "beyond"
    summary.append(
        f"{area}: refitting the tree models with {seeds} seeds moves their RMSE by up to "
        f"±{fmt(floor)}, so the gap between the best two ({fmt(gap)}) is {within} that noise."
    )
    beaten = [
        LABELS[f.name] for f in fitted if f.test["RMSE"] >= min(b["RMSE"] for b in base.values())
    ]
    summary.append(
        f"{area}: "
        + (
            "every model beats both baselines."
            if not beaten
            else f"{', '.join(beaten)} do not beat the better baseline, so they add little."
        )
    )
    if len(windows) > 1:
        summary.append(
            f"{area}: over {len(windows)} test windows of {test_years} years, mean RMSE "
            + ", ".join(
                f"{LABELS[f.name]} {fmt(np.mean([w['RMSE'] for w in f.rolling]))} "
                f"(±{fmt(np.std([w['RMSE'] for w in f.rolling]))})"
                for f in fitted
            )
            + "."
        )
    return Forecast(
        chosen,
        (f"{first:%Y-%m}", f"{last:%Y-%m}"),
        (test_start[:7], f"{end:%Y-%m}"),
        [d.strftime("%Y-%m-%d") for d in X.index[~train]],
        [float(v) for v in y_[~train]],
        fitted,
        base,
        summary,
    )
