"""Methodological checks written as code (requirement AI-03).

Each check looks at an analysis the researcher has made and says, in one sentence, when its
result should not be read at face value: two seasonal series correlated without removing the
season, too few months for a test to mean much, a driver measured over a footprint larger
than the area, a "best" model whose lead is within noise or changes with the test period, a
model that does not beat climatology. The same sentences go on the card and to Magonia, so
the assistant warns about what the card warns about. Nothing here changes a result.
"""

import numpy as np
import pandas as pd

# A series whose calendar-month means explain more than half its variance is seasonal
SEASONAL = 0.5
# Fewer months than this leave a correlation or a trend test with little power
MIN_MONTHS = 36
MIN_DECOMPOSITION_YEARS = 4
MIN_TEST_MONTHS = 24


def seasonal_share(series: pd.Series) -> float:
    """Share of a monthly series' variance explained by its calendar-month means."""
    s = series.dropna()
    if len(s) < 24 or s.var() == 0:
        return 0.0
    normal = s.groupby(s.index.month).transform("mean")
    return float(1 - (s - normal).var() / s.var())


def footprint(title: str, warnings: list[str]) -> list[str]:
    """A product's own warning that its pixel is larger than the area, carried to the analyses
    that use it."""
    return [f"{title}: {w}" for w in warnings if "pixel" in w]


def correlation(
    area: str,
    response: tuple[str, pd.Series],
    driver: tuple[str, pd.Series],
    deseasonalised: bool,
    months: int,
) -> list[str]:
    (rt, r), (dt, d) = response, driver
    out = []
    if not deseasonalised and min(seasonal_share(r), seasonal_share(d)) > SEASONAL:
        out.append(
            f"{area}: {rt} and {dt} both follow a yearly cycle ({100 * seasonal_share(r):.0f}% "
            f"and {100 * seasonal_share(d):.0f}% of their variance), and it was not removed, so "
            "most of the correlation is the shared season. Tick 'Remove seasonal cycle' to see "
            "the link beyond it."
        )
    if months < MIN_MONTHS:
        out.append(
            f"{area}: only {months} months in common; a correlation needs about {MIN_MONTHS} to "
            "mean much."
        )
    return out


def lags(
    area: str,
    response: tuple[str, pd.Series],
    drivers: list[tuple[str, pd.Series, list[str]]],
    deseasonalised: bool,
) -> list[str]:
    title, y = response
    out = []
    months = int(y.notna().sum())
    if months < MIN_MONTHS:
        out.append(
            f"{area}: only {months} months of {title}; the lag test needs about {MIN_MONTHS} to "
            "mean much."
        )
    if not deseasonalised:
        seasonal = [
            name for name, x, _ in drivers if min(seasonal_share(y), seasonal_share(x)) > SEASONAL
        ]
        if seasonal or seasonal_share(y) > SEASONAL:
            out.append(
                f"{area}: the seasonal cycle was kept, so the memory and "
                + (f"the links with {', '.join(seasonal)} " if seasonal else "the links ")
                + "mostly repeat the season; tick 'Remove seasonal cycle' to test beyond it."
            )
    for name, _, warnings in drivers:
        out += [f"{area}: {w}" for w in footprint(name, warnings)]
    return out


def decomposition(area: str, title: str, years: float) -> list[str]:
    if years < MIN_DECOMPOSITION_YEARS:
        why = (
            f"{area}, {title}: only {years:.1f} years; a trend kept from cycles longer than a "
            f"year needs about {MIN_DECOMPOSITION_YEARS} to be told apart from them."
        )
        return [why]
    return []


LABELS = {"Ridge": "Ridge", "RandomForest": "Random Forest", "XGBoost": "XGBoost"}


def models(area: str, forecast: dict, warnings: list[str] | None = None) -> list[str]:
    """Cautions on a forecast's results, as the engine's forecast returns them."""
    out = []
    fitted = sorted(forecast["models"], key=lambda m: m["test"]["RMSE"])
    base = forecast["baselines"]
    best_base = min(base, key=lambda b: base[b]["RMSE"])
    unskilled = [m for m in fitted if m["test"]["RMSE"] >= base[best_base]["RMSE"]]
    if unskilled and len(unskilled) == len(fitted):
        out.append(
            f"{area}: no model beats {best_base} (RMSE {base[best_base]['RMSE']:.4f}); the "
            "forecasts add nothing a calendar or last month's value would not give, so what the "
            "models lean on says little about the area."
        )
    elif unskilled:
        names = ", ".join(LABELS[m["name"]] for m in unskilled)
        out.append(
            f"{area}: {names} {'do' if len(unskilled) > 1 else 'does'} not beat {best_base}."
        )
    if len(fitted) > 1:
        gap = fitted[1]["test"]["RMSE"] - fitted[0]["test"]["RMSE"]
        trees = [m["seeds"]["RMSE_sd"] for m in fitted[:2] if m["seeds"].get("runs", 1) > 1]
        if trees and gap <= 2 * max(trees):
            out.append(
                f"{area}: {LABELS[fitted[0]['name']]} and {LABELS[fitted[1]['name']]} differ by "
                f"{gap:.4f}, within twice the seed noise (±{max(trees):.4f}); neither is better."
            )
        spread = [
            float(np.std([w["RMSE"] for w in m["rolling"]]))
            for m in fitted[:2]
            if len(m.get("rolling", [])) > 1
        ]
        if spread and gap < max(spread):
            out.append(
                f"{area}: which model is best depends on the test period: the gap between the "
                f"best two ({gap:.4f}) is smaller than how much their error varies across "
                f"earlier windows (±{max(spread):.4f})."
            )
    if len(forecast["observed"]) < MIN_TEST_MONTHS:
        out.append(
            f"{area}: only {len(forecast['observed'])} test months; scores on so few months move "
            "a lot with the period chosen."
        )
    out += [f"{area}: {w}" for w in warnings or []]
    return out
