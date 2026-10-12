"""Magonia must reproduce the paper's extraction (SRS section 8.1, NFR-T2).

By default the Earth Engine responses are replayed from tests/data/recorded, so
this runs in CI. Run with -m live to ask Earth Engine again.
"""

import json

import pandas as pd
import pytest
from acceptance_cases import CASES, DATA, RECORDED, orchard

from engine.earth_engine import connect
from engine.pipeline import Request, run
from engine.series import fetch


def replay(name):
    def recorded(*args):
        return json.loads((RECORDED / f"{name}.json").read_text())

    return recorded


def request(name, resolution="native"):
    case = CASES[name]
    return Request(
        case.variable,
        orchard(),
        case.start,
        case.end,
        case.masking,
        case.scale,
        resolution,
        max_gap=0,
    )


def check_native(name, result):
    case = CASES[name]
    reference = pd.read_csv(DATA / case.reference, parse_dates=["date"])
    table = result.table
    assert list(table["date"]) == list(reference["date"])
    assert list(table["masked"]) == list(reference[case.column].isna())
    expected = reference[case.column].to_numpy()
    assert table["value"].to_numpy() == pytest.approx(expected, abs=1e-6, nan_ok=True)


@pytest.mark.parametrize("name", CASES)
def test_reproduces_the_reference(name):
    check_native(name, run(request(name), fetch=replay(name)))


@pytest.mark.parametrize("name", CASES)
def test_monthly_series_reproduces_the_reference(name):
    result = run(request(name, "monthly"), fetch=replay(name))
    reference = pd.read_csv(DATA / "reference_monthly.csv", parse_dates=["date"])
    assert list(result.table["date"]) == list(reference["date"])
    expected = reference[CASES[name].column].to_numpy()
    assert result.table["value"].to_numpy() == pytest.approx(expected, abs=1e-6)


@pytest.mark.live
@pytest.mark.parametrize("name", CASES)
def test_live_reproduces_the_reference(name):
    connect()
    check_native(name, run(request(name), fetch=fetch))
