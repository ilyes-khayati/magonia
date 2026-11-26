"""Seasonal ARIMA with the drivers as regressors: the research's interpretable reference.

As in the research (notebook 04), the orders are chosen on the training months by a rule fixed
in advance, before any machine-learning model is fitted:

- seasonal differencing when the STL seasonal strength exceeds 0.64 (Wang et al., 2006);
- ordinary differencing until the ADF and KPSS tests agree that the series is stationary;
- p and q from 0 to 2 and P and Q from 0 to 1, the combination with the lowest AIC.

The coefficients are then estimated on the training months with the drivers' lagged values as
regressors (a regression with SARIMA errors), and the filter is run through the test months
with those coefficients fixed: each month is forecast from the months before it only, as the
other models are.
"""

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import adfuller, kpss

SEASONAL_STRENGTH = 0.64  # above it, the seasonal cycle is differenced away


@dataclass
class Spec:
    order: tuple[int, int, int]
    seasonal_order: tuple[int, int, int, int]
    trend: str  # "c" with a constant when nothing is differenced, else "n"

    def to_dict(self) -> dict:
        return {
            "order": list(self.order),
            "seasonal_order": list(self.seasonal_order),
            "trend": self.trend,
        }


@dataclass
class Reference:
    spec: Spec
    predictions: pd.Series  # one month ahead, over the months asked for
    coefficients: list[dict] = field(default_factory=list)  # term, value, p, effect of 1 sd
    ljung_box: dict = field(default_factory=dict)  # p-values of residual autocorrelation


def seasonal_strength(y: pd.Series) -> float:
    fit = STL(y.interpolate(limit_direction="both"), period=12, robust=True).fit()
    return max(0.0, 1 - np.var(fit.resid) / np.var(fit.resid + fit.seasonal))


def choose_d(x: np.ndarray) -> int:
    for d in range(3):
        z = np.diff(x, d) if d else x
        if adfuller(z, autolag="AIC")[1] < 0.05 and kpss(z, regression="c", nlags="auto")[1] > 0.05:
            return d
    return 2


def select_order(y: pd.Series) -> Spec:
    """The rule of the research, applied to the training months only."""
    # statsmodels warns when an optimiser stops early or start values look non-stationary; the
    # fits are kept, and the residual check judges them
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        D = int(seasonal_strength(y) > SEASONAL_STRENGTH)
        d = choose_d((y.diff(12) if D else y).dropna().to_numpy())
        trend = "c" if d + D == 0 else "n"
        fits = []
        for p in range(3):
            for q in range(3):
                for P in range(2):
                    for Q in range(2):
                        try:
                            r = SARIMAX(
                                y, order=(p, d, q), seasonal_order=(P, D, Q, 12), trend=trend
                            ).fit(disp=False)
                            fits.append((r.aic, (p, d, q), (P, D, Q, 12)))
                        except (ValueError, np.linalg.LinAlgError):
                            continue
    if not fits:
        raise ValueError("no seasonal ARIMA could be fitted to the training months")
    _, order, seasonal = min(fits)
    return Spec(order, seasonal, trend)


def regressors(X: pd.DataFrame, own: str) -> list[str]:
    """The drivers' lagged values: not the response's own lags, which the ARIMA part models,
    and not the calendar, which the seasonal part models."""
    return [c for c in X.columns if not c.startswith(f"{own}_lag") and not c.startswith("month_")]


def monthly(X: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Regular monthly steps. A month missing from the table stays missing in the response,
    which the filter skips; the regressors are interpolated there, as the filter needs a value."""
    y = y.asfreq("MS")
    X = X.asfreq("MS").interpolate(limit_direction="both")
    return X, y


def reference(X: pd.DataFrame, y: pd.Series, test_start: str, end: str | None = None) -> Reference:
    """Orders and coefficients from the months before test_start, then one-month-ahead
    forecasts from test_start to end (the last month by default)."""
    columns = regressors(X, str(y.name))
    X, y = monthly(X[columns], y)
    train = y.index < test_start
    y_train, X_train = y[train], X[train]
    spec = select_order(y_train)
    exog = X_train if columns else None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(
            y_train,
            exog=exog,
            order=spec.order,
            seasonal_order=spec.seasonal_order,
            trend=spec.trend,
        ).fit(disp=False)
        # the coefficients stay fixed; the filter only reads each month as it comes
        run = fit.apply(y, exog=X if columns else None, refit=False)
    last = end or y.index.max()
    predictions = run.predict(start=pd.Timestamp(test_start), end=pd.Timestamp(last))
    d, D = spec.order[1], spec.seasonal_order[1]
    k = spec.order[0] + spec.order[2] + spec.seasonal_order[0] + spec.seasonal_order[2]
    residuals = fit.resid[d + 12 * D :].dropna()
    lb = acorr_ljungbox(residuals, lags=[12, 24], model_df=k)["lb_pvalue"]
    coefficients = [
        {
            "term": term,
            "value": float(fit.params[term]),
            "p": float(fit.pvalues[term]),
            "effect_of_1sd": float(fit.params[term] * X_train[term].std()),
        }
        for term in columns
    ]
    return Reference(
        spec, predictions, coefficients, {"12": float(lb.iloc[0]), "24": float(lb.iloc[1])}
    )
