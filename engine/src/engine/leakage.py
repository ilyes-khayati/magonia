"""How much of a wavelet-hybrid forecast's skill comes from the future.

Wavelet-hybrid forecasting decomposes a series into a trend and a seasonal part, then predicts
the next value from past values of those parts. When the whole record is decomposed at once,
the wavelet filter, which is two-sided, puts information from later months into each month's
parts: last month's trend already "knows" this month. The forecast looks better than any
forecast made at the time could be.

The audit fits the same models on the same lags of the parts, decomposed two ways: over the
whole record, as is usual, and causally, each month from the data up to that month only. The
difference in test error is the leakage. Lags of the raw series give the honest reference.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from engine.decompose import split
from engine.models import baselines, estimator, scores

ORDER = ("Ridge", "RandomForest", "XGBoost")

LEVEL = 4  # monthly: the trend keeps cycles longer than about a year, as decompose chooses
WARMUP = 48  # months decomposed before the first causal value is trusted
LAGS = (1, 2, 3, 6, 12)
MIN_MONTHS = 96


class LeakageError(ValueError):
    pass


@dataclass
class Leakage:
    test: tuple[str, str]
    rows: list[dict]  # per model: part R² and value RMSE, decomposed both ways, and raw lags
    placebo: dict[str, float]  # trend R² on white noise of the same length, both ways
    baselines: dict[str, float]  # RMSE of persistence and climatology on the test years
    dates: list[str]  # test months
    observed: list[float]
    whole: list[float]  # the best model's forecasts with whole-record parts
    causal: list[float]  # ...with causal parts
    best: str
    summary: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def causal_parts(
    values: np.ndarray, level: int = LEVEL, warmup: int = WARMUP
) -> tuple[np.ndarray, np.ndarray]:
    """Each month's trend and seasonal part from the data up to that month only."""
    trend = np.full(len(values), np.nan)
    for t in range(warmup - 1, len(values)):
        trend[t] = split(values[: t + 1], level)[0][-1]
    return trend, values - trend


def lagged(parts: pd.DataFrame, lags=LAGS) -> pd.DataFrame:
    return pd.concat({f"{c}_lag{k}": parts[c].shift(k) for c in parts for k in lags}, axis=1)


def longest_run(y: pd.Series) -> pd.Series:
    """Monthly, short gaps filled by straight lines, then the longest stretch without one."""
    y = y.asfreq("MS").interpolate(limit=2, limit_area="inside")
    ok = y.notna().to_numpy()
    best, start = (0, 0), None
    for i, good in enumerate(np.append(ok, False)):
        if good and start is None:
            start = i
        elif not good and start is not None:
            best = max(best, (start, i), key=lambda r: r[1] - r[0])
            start = None
    return y.iloc[best[0] : best[1]]


def hybrid(
    y: pd.Series, parts: dict[str, pd.DataFrame], usable: pd.Series, name: str, test_years: int
):
    """The published recipe: each part forecast from lags of the parts, the forecasts added.
    Returns, per way of decomposing, the R² of each part's forecast and the summed forecast."""
    index = y.index[usable]
    test_start = index[-1] - pd.DateOffset(years=test_years) + pd.DateOffset(months=1)
    train = index < test_start
    out = {}
    for way, frame in parts.items():
        X = lagged(frame).loc[index]
        total, r2 = 0.0, {}
        for part in frame:
            target = frame[part].loc[index]
            model = estimator(name, {}).fit(X[train], target[train])
            p = model.predict(X[~train])
            r2[part] = scores(target[~train], p)["R2"]
            total = total + p
        out[way] = (r2, np.asarray(total))
    return out, index, train


def ways(values: np.ndarray, index: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    whole = split(values, LEVEL)
    causal = causal_parts(values)
    return {
        way: pd.DataFrame({"trend": t, "seasonal": s}, index=index)
        for way, (t, s) in {"whole": whole, "causal": causal}.items()
    }


def audit(
    y: pd.Series,
    title: str,
    area: str,
    test_years: int = 3,
    models: tuple[str, ...] = ("Ridge", "RandomForest", "XGBoost"),
) -> Leakage:
    """y: monthly values indexed by month start."""
    y = longest_run(y.rename("value"))
    if len(y) < MIN_MONTHS:
        raise LeakageError(
            f"{area}: {title} has {len(y)} consecutive months; the audit needs {MIN_MONTHS}, "
            f"so that {WARMUP} can be spent before the first causal decomposition."
        )
    values = y.to_numpy(float)
    parts = ways(values, y.index)
    raw = pd.concat({f"value_lag{k}": y.shift(k) for k in LAGS}, axis=1)
    usable = parts["causal"]["trend"].notna() & lagged(parts["causal"]).notna().all(axis=1)
    usable &= raw.notna().all(axis=1)

    rows, sums = [], {}
    for name in [m for m in ORDER if m in models]:
        found, index, train = hybrid(y, parts, usable, name, test_years)
        target = y.loc[index]
        X = raw.loc[index]
        plain = estimator(name, {}).fit(X[train], target[train]).predict(X[~train])
        rows.append(
            {
                "model": name,
                "trend_whole": found["whole"][0]["trend"],
                "trend_causal": found["causal"][0]["trend"],
                "seasonal_whole": found["whole"][0]["seasonal"],
                "seasonal_causal": found["causal"][0]["seasonal"],
                "whole": scores(target[~train], found["whole"][1])["RMSE"],
                "causal": scores(target[~train], found["causal"][1])["RMSE"],
                "raw": scores(target[~train], plain)["RMSE"],
            }
        )
        sums[name] = found

    # the placebo: the same recipe on white noise of the same length, where nothing at all
    # can be forecast; any trend skill there comes from the decomposition, not the data
    noise = pd.Series(np.random.default_rng(0).normal(size=len(values)), index=y.index)
    noise_parts = ways(noise.to_numpy(), y.index)
    noise_found, _, _ = hybrid(noise, noise_parts, usable, "Ridge", test_years)
    placebo = {way: noise_found[way][0]["trend"] for way in ("whole", "causal")}

    reference = baselines(target, pd.Series(train, index=index))
    base = {
        k: scores(target[~train], v[~train].fillna(target[train].mean()))["RMSE"]
        for k, v in reference.items()
    }
    best = min(rows, key=lambda r: r["causal"])["model"]
    test_dates = index[~train]
    return Leakage(
        test=(f"{test_dates[0]:%Y-%m}", f"{test_dates[-1]:%Y-%m}"),
        rows=rows,
        placebo=placebo,
        baselines=base,
        dates=[f"{d:%Y-%m}" for d in test_dates],
        observed=[round(float(v), 4) for v in target[~train]],
        whole=[round(float(v), 4) for v in sums[best]["whole"][1]],
        causal=[round(float(v), 4) for v in sums[best]["causal"][1]],
        best=best,
        summary=describe(area, title, rows, placebo, base, best),
    )


LABELS = {"Ridge": "Ridge", "RandomForest": "Random Forest", "XGBoost": "XGBoost"}


def describe(area, title, rows, placebo, base, best) -> list[str]:
    row = next(r for r in rows if r["model"] == best)
    persistence = base["persistence"]
    raw_best = min(rows, key=lambda r: r["raw"])
    gap = (row["causal"] - row["whole"]) / row["causal"]
    parts = (
        f"{area}: forecast part by part, {LABELS[best]}'s trend forecast reaches R² "
        f"{row['trend_whole']:.2f} when the whole record is decomposed at once and "
        f"{row['trend_causal']:.2f} when each month is decomposed from the past only."
    )
    noise = (
        f"{area}: on white noise, where nothing can be forecast, the same recipe reaches trend "
        f"R² {placebo['whole']:.2f} with whole-record parts and {placebo['causal']:.2f} with "
        "causal ones: what the whole-record trend score adds comes from later months, not skill."
    )
    value = (
        f"{area}: for {title} itself, the parts added back give RMSE {row['whole']:.4f} "
        f"decomposed at once and {row['causal']:.4f} from the past only "
        f"({gap:+.0%} of the honest error); lags of {title} with no decomposition give "
        f"{raw_best['raw']:.4f}, persistence {persistence:.4f}."
    )
    return [parts, noise, value]
