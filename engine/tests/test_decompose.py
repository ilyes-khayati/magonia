"""The decomposition must reproduce the 2026 paper's (notebook 02), as the extraction does."""

import json

import numpy as np
import pandas as pd
import pytest
from acceptance_cases import CASES, DATA, RECORDED, orchard

from engine.decompose import DecompositionError, decompose, level_for, semi_period
from engine.pipeline import Request, run


def test_levels_put_the_boundary_nearest_one_year_as_in_the_papers():
    assert {
        key: level_for(days) for key, days in [("ndvi", 16), ("lst", 8), ("spei", 365.25 / 12)]
    } == {
        "ndvi": 5,
        "lst": 6,
        "spei": 4,
    }
    assert 300 < semi_period(5, 16) < 450


def test_trend_and_seasonal_add_back_to_the_series():
    dates = pd.Series(pd.date_range("2010-01-01", periods=120, freq="MS"))
    rng = np.random.default_rng(0)
    values = pd.Series(
        np.sin(np.arange(120) * 2 * np.pi / 12) + np.arange(120) / 60 + rng.normal(0, 0.1, 120)
    )
    monthly = decompose(dates, values, "spei").monthly
    assert np.allclose(monthly.trend + monthly.seasonal, monthly.value)
    # the trend follows the slow rise (1.8 between the first and last years), a little
    # flattened at the ends by the mirroring, and not the yearly cycle
    assert monthly.trend.iloc[-12:].mean() - monthly.trend.iloc[:12].mean() > 1.2
    assert monthly.trend.diff().abs().max() < 0.2


def test_gaps_inside_are_filled_and_counted_and_ends_dropped():
    dates = pd.Series(pd.date_range("2010-01-01", periods=60, freq="MS"))
    values = pd.Series(np.sin(np.arange(60) / 2.0))
    values[[0, 1, 30, 31]] = np.nan
    result = decompose(dates, values, "spei")
    assert result.interpolated == 2
    assert result.monthly.date.iloc[0] == pd.Timestamp("2010-03-01")


def test_too_short_a_series_is_refused():
    dates = pd.Series(pd.date_range("2020-01-01", periods=24, freq="MS"))
    with pytest.raises(DecompositionError, match="three years"):
        decompose(dates, pd.Series(np.ones(24)), "spei")


@pytest.mark.parametrize(
    ("name", "key", "column"),
    [("ndvi", "ndvi", "NDVI"), ("lst", "lst", "LST"), ("spei_3", "spei", "SPEI_3")],
)
def test_reproduces_the_papers_decomposition(name, key, column):
    case = CASES[name]
    request = Request(
        case.variable,
        orchard(),
        case.start,
        case.end,
        case.masking,
        case.scale,
        "native",
        max_gap=0,
    )
    table = run(
        request, fetch=lambda *args: json.loads((RECORDED / f"{name}.json").read_text())
    ).table
    ours = decompose(table.date, table.value, key).monthly.set_index("date")
    paper = pd.read_csv(DATA / "reference_decomposition.csv", parse_dates=["date"]).set_index(
        "date"
    )
    both = ours.join(paper, how="inner")
    assert len(both) == 298
    assert np.allclose(both.trend, both[f"{column}_T"], atol=1e-9)
    assert np.allclose(both.seasonal, both[f"{column}_S"], atol=1e-9)
