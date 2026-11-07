import numpy as np
import pandas as pd
import pytest

from engine.coherence import CoherenceError, coherence

MONTHS = pd.date_range("2001-01-01", periods=288, freq="MS")


def series(values):
    return pd.Series(values, MONTHS)


def test_a_lagged_annual_cycle_is_coherent_and_its_lead_is_found():
    t = np.arange(288)
    rng = np.random.default_rng(1)
    a = np.sin(2 * np.pi * t / 12) + 0.3 * rng.normal(size=288)
    b = np.sin(2 * np.pi * (t - 2) / 12) + 0.3 * rng.normal(size=288)  # b follows a by two months
    found = coherence(series(a), series(b), "NDVI", "LST", "Orchard", runs=100)
    assert "coherent 100% of the time" in found.summary[0]
    assert "about 2.0 months, NDVI leading" in found.summary[1]


def test_unrelated_noise_is_rarely_called_coherent():
    rng = np.random.default_rng(2)
    found = coherence(
        series(rng.normal(size=288)), series(rng.normal(size=288)), "A", "B", "Orchard", runs=100
    )
    significant = np.array(found.significant)
    inside = np.array(found.periods)[:, None] <= np.array(found.coi)[None, :]
    assert significant[inside].mean() < 0.1  # about the 5% a 95% level allows


def test_short_records_are_refused():
    short = pd.Series(np.arange(24.0), MONTHS[:24])
    with pytest.raises(CoherenceError, match="at least 36"):
        coherence(short, short, "A", "B", "Orchard")


def test_the_longest_run_of_months_both_series_have_is_used():
    rng = np.random.default_rng(3)
    a = series(rng.normal(size=288))
    a.iloc[100:110] = np.nan  # a gap too long to fill
    found = coherence(a, series(rng.normal(size=288)), "A", "B", "Orchard", runs=20)
    assert found.times[0] == "2010-03" and len(found.times) == 178
