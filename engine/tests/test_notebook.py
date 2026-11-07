import json

import pandas as pd
import pytest
from acceptance_cases import DATA

from engine.notebook import dumps, notebook


def series(column, key, title):
    d = pd.read_csv(DATA / "reference_decomposition.csv", parse_dates=["date"])
    points = [
        {"date": f"{t:%Y-%m-%d}", "value": float(v), "masked": False, "filled": False}
        for t, v in zip(d["date"], d[column])
    ]
    return {"area": "Orchard", "key": key, "title": title, "units": "", "points": points}


class Anything:
    """Stands in for matplotlib, which the engine does not need: every call does nothing."""

    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        grid = len(args) == 2 and all(isinstance(a, int) for a in args)  # subplots(2, 1)
        return (self, self) if grid else self

    def __iter__(self):
        return iter((self, self))


@pytest.fixture(autouse=True)
def no_plots(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "matplotlib", Anything())
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", Anything())


def run(nb, skip=()):
    """Every code cell in one namespace, as Jupyter would, except the slow ones named."""
    space = {"display": print}
    for cell in nb["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] == "code" and not any(s in source for s in skip):
            exec(compile(source, "<cell>", "exec"), space)  # noqa: S102 - the notebook under test
    return space


@pytest.mark.filterwarnings("ignore")
def test_an_exported_experiment_runs_and_gives_the_same_forecast():
    from engine.facts import Series, monthly_series
    from engine.models import forecast

    used = [series("NDVI", "ndvi", "NDVI"), series("LST", "lst", "LST")]
    options = {"own_lags": [1, 12], "test_years": 3, "models": ["Ridge"], "rolling": False}
    nb = notebook("Orchard forecast", "experiment", options, used)
    assert json.loads(dumps(nb))["nbformat"] == 4
    space = run(nb, skip=["explain("])
    s = {u["key"]: Series(u["area"], u["key"], u["title"], u["units"], u["points"]) for u in used}
    direct = forecast(
        "Orchard",
        ("NDVI", "ndvi", monthly_series(s["ndvi"])),
        [("LST", "lst", monthly_series(s["lst"]))],
        own_lags=[1, 12],
        models=["Ridge"],
        rolling=False,
    )
    assert space["found"].summary == direct.summary


@pytest.mark.filterwarnings("ignore")
@pytest.mark.parametrize("kind", ["trend", "lags", "correlation", "decomposition", "scales"])
def test_each_analysis_exports_a_notebook_that_runs(kind):
    used = [series("NDVI", "ndvi", "NDVI"), series("LST", "lst", "LST")]
    if kind == "scales":
        used = [
            series("NDVI", "ndvi", "NDVI"),
            series("LST", "spei", "SPEI-1"),
            series("LST", "spei", "SPEI-3"),
        ]
    if kind in ("trend", "decomposition"):
        used = used[:1]
    run(notebook(f"Orchard {kind}", kind, {"deseasonalise": True}, used))
