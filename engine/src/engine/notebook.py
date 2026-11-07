"""An analysis exported as a Jupyter notebook that reproduces it (requirement REP-01).

The notebook carries the series exactly as Magonia used them, with where they came from, and
calls the same engine functions with the same choices, so that running it gives the same
numbers without Earth Engine. It is written as plain JSON in the notebook format (version 4),
so nothing beyond the standard library is needed to make it.
"""

import json
from datetime import UTC, datetime

import engine

INSTALL = (
    "# The Magonia engine and what the plots need, once per environment. The engine is the\n"
    "# engine/ folder of the Magonia repository, at the version that made this notebook:\n"
    f"# pip install ./engine matplotlib   (engine {engine.__version__})\n"
)


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.strip("\n").splitlines(True),
    }


def csv(points: list[dict]) -> str:
    rows = ["date,value,masked,filled"]
    rows += [
        f"{p['date']},{'' if p['value'] is None else p['value']},{p['masked']},{p['filled']}"
        for p in points
    ]
    return "\n".join(rows)


def data_cells(series: list[dict]) -> list[dict]:
    """The series as used, one CSV each, read back into the engine's own form."""
    lines = ["import io", "", "import pandas as pd", "from engine import facts", "", "SERIES = {}"]
    for s in series:
        name = f"{s['area']} {s['title']}"
        lines += [
            f"SERIES[{name!r}] = facts.Series(",
            f"    {s['area']!r}, {s['key']!r}, {s['title']!r}, {s['units']!r},",
            "    pd.read_csv(io.StringIO('''" + csv(s["points"]) + "'''))",
            "    .astype({'masked': bool, 'filled': bool})",
            "    .replace({float('nan'): None})",
            "    .to_dict('records'),",
            f"    resolution={s.get('resolution', 'monthly')!r},",
            ")",
        ]
    return [code("\n".join(lines))]


def provenance(series: list[dict], options: dict) -> str:
    rows = "\n".join(
        f"| {s['area']} | {s['title']} | {s.get('product', '')} | {s.get('resolution', '')} | "
        f"{len(s['points'])} |"
        for s in series
    )
    choices = ", ".join(f"{k} = {v}" for k, v in options.items() if v not in (None, "", []))
    return (
        "| Area | Variable | Product | Time step | Values |\n|---|---|---|---|---|\n"
        f"{rows}\n\nChoices: {choices or 'defaults'}."
    )


def analysis_cells(kind: str, options: dict, series: list[dict]) -> list[dict]:
    """The call that reproduces the analysis, and a plot of what it found."""
    first = series[0]

    def key(s: dict) -> str:
        return f"{s['area']} {s['title']}"

    if kind == "experiment":
        response = key(first)
        drivers = [key(s) for s in series[1:]]
        call = f"""
from engine.models import forecast

target = SERIES[{response!r}]
drivers = [SERIES[name] for name in {drivers!r}]
found = forecast(
    target.area,
    (target.title, target.key, facts.monthly_series(target)),
    [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
    own_lags={options.get("own_lags")!r},
    driver_lags={options.get("driver_lags")!r},
    test_years={options.get("test_years", 3)!r},
    models={options.get("models", ["Ridge", "RandomForest", "XGBoost"])!r},
    params={options.get("params") or None!r},
    calendar={options.get("calendar", True)!r},
    rolling={options.get("rolling", True)!r},
)
for line in found.summary:
    print(line)
"""
        plot = """
import matplotlib.pyplot as plt

dates = pd.to_datetime(found.dates)
plt.figure(figsize=(9, 3.5))
plt.plot(dates, found.observed, color="black", linewidth=2, label="observed")
for model in found.models:
    plt.plot(dates, model.predictions, linewidth=1.2, label=f"{model.name} (RMSE {model.test['RMSE']:.4f})")
plt.legend()
plt.title(f"{target.area}: {target.title} one month ahead, test period")
plt.tight_layout()
"""
        explain = (
            """
from engine.explain import describe, explain
from engine.models import design

X, y, _, test_start = design(
    (target.title, target.key, facts.monthly_series(target)),
    [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
    """
            + f"{options.get('own_lags')!r}, {options.get('driver_lags')!r}, {options.get('test_years', 3)!r}, {options.get('calendar', True)!r},"
            + """
)
train = X.index < test_start
explained = explain(X[train], y[train], {m.name: m.params for m in found.models})
for line in describe(target.area, explained):
    print(line)
"""
        )
        return [
            markdown("## The forecast"),
            code(call),
            code(plot),
            markdown(
                "## What each model leans on\n\nPermutation importance on the training years, as in the paper; this takes a minute or two."
            ),
            code(explain),
        ]
    if kind == "decomposition":
        return [
            markdown("## Trend and season"),
            code(
                """
from engine.decompose import decompose
import matplotlib.pyplot as plt

for name, s in SERIES.items():
    frame = pd.DataFrame(s.points)
    values = frame["value"].where(~frame["masked"] | frame["filled"])
    parts = decompose(frame["date"], values, s.key)
    m = parts.monthly
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(9, 4.5), sharex=True)
    top.plot(m["date"], m["value"], linewidth=0.8, alpha=0.5, label=s.title)
    top.plot(m["date"], m["trend"], linewidth=2, label="trend")
    bottom.plot(m["date"], m["seasonal"], linewidth=1, label="seasonal part")
    top.set_title(f"{s.area}: {s.title}, wavelet level {parts.level}")
    top.legend(); bottom.legend(); plt.tight_layout()
    for fact in facts.decomposition_facts("", s):
        print(fact.text)
"""
            ),
        ]
    if kind == "trend":
        return [
            markdown("## Long-term trend"),
            code(
                """
from engine.trend import trend
import matplotlib.pyplot as plt

plt.figure(figsize=(8, 3.5))
for name, s in SERIES.items():
    found = trend(s.area, s.title, s.key, s.units, s.points)
    years = sorted(found.years)
    plt.plot(years, [found.years[y] for y in years], marker="o", label=s.area)
    if found.slope is not None:
        plt.plot(years, [found.intercept + found.slope / 10 * (y - years[0]) for y in years], "--")
    for line in found.summary + found.cautions:
        print(line)
plt.legend(); plt.title("Annual means and Theil–Sen lines"); plt.tight_layout()
"""
            ),
        ]
    if kind == "phenology":
        return [
            markdown("## Season dates"),
            code(
                """
from engine.phenology import phenology

for name, s in SERIES.items():
    found = phenology(s.area, s.title, s.key, s.points)
    display(pd.DataFrame([vars(season) for season in found.seasons]))
    for line in found.summary + found.cautions:
        print(line)
"""
            ),
        ]
    if kind == "lags":
        response = key(first)
        drivers = [key(s) for s in series[1:]]
        return [
            markdown("## Memory and lags"),
            code(
                f"""
from engine.lags import explore

target = SERIES[{response!r}]
drivers = [SERIES[name] for name in {drivers!r}]
found = explore(
    target.area,
    (target.title, target.key, facts.monthly_series(target)),
    [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
    {options.get("deseasonalise", True)!r},
)
for line in found.summary:
    print(line)
"""
            ),
        ]
    if kind == "correlation":
        return [
            markdown("## Correlation and lag"),
            code(
                f"""
for area in dict.fromkeys(s.area for s in SERIES.values()):
    pair = [s for s in SERIES.values() if s.area == area]
    if len(pair) == 2:
        print(facts.correlation_fact("", pair[0], pair[1], {options.get("deseasonalise", True)!r}).text)
"""
            ),
        ]
    if kind == "scales":
        scales = [key(s) for s in series[1:]]
        return [
            markdown("## Drought scale and lag"),
            code(
                f"""
target = SERIES[{key(first)!r}]
scales = [SERIES[name] for name in {scales!r}]
for title, lag in facts.scale_scan(target, scales, deseasonalise={options.get("deseasonalise", True)!r}):
    print(f"{{title}}, {{lag.lag}} months earlier: r = {{lag.r:.2f}} (n = {{lag.n}})")
print(facts.scale_fact("", target, scales, {options.get("deseasonalise", True)!r}).text)
"""
            ),
        ]
    raise ValueError(f"no notebook for {kind!r}")


def notebook(title: str, kind: str, options: dict, series: list[dict]) -> dict:
    """series: area, key, title, units, points, and optionally product and resolution."""
    intro = markdown(
        f"# {title}\n\nExported from Magonia on {datetime.now(UTC):%d %B %Y}, engine "
        f"{engine.__version__}. Running it reproduces the analysis from the data below, without "
        f"Earth Engine.\n\n{provenance(series, options)}"
    )
    cells = [intro, code(INSTALL), markdown("## The data, as Magonia used it"), *data_cells(series)]
    cells += analysis_cells(kind, options, series)
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python"},
            "magonia": {"kind": kind, "options": options, "engine": engine.__version__},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def dumps(nb: dict) -> str:
    return json.dumps(nb, indent=1, ensure_ascii=False)
