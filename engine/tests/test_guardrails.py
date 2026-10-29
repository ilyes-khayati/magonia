import numpy as np
import pandas as pd

from engine import guardrails

INDEX = pd.date_range("2005-01-01", periods=120, freq="MS")
RNG = np.random.default_rng(0)
SEASONAL = pd.Series(np.sin(2 * np.pi * INDEX.month / 12) + 0.1 * RNG.normal(size=120), INDEX)
NOISE = pd.Series(RNG.normal(size=120), INDEX)


def test_seasonal_share_tells_a_yearly_cycle_from_noise():
    assert guardrails.seasonal_share(SEASONAL) > 0.9
    assert guardrails.seasonal_share(NOISE) < 0.2


def test_correlating_two_seasonal_series_without_removing_the_season_is_flagged():
    found = guardrails.correlation("Orchard", ("NDVI", SEASONAL), ("LST", -SEASONAL), False, 120)
    assert len(found) == 1 and "most of the correlation is the shared season" in found[0]
    assert (
        guardrails.correlation("Orchard", ("NDVI", SEASONAL), ("LST", -SEASONAL), True, 120) == []
    )
    assert guardrails.correlation("Orchard", ("NDVI", NOISE), ("LST", NOISE), False, 120) == []


def test_too_few_months_are_flagged():
    found = guardrails.correlation("Orchard", ("NDVI", NOISE), ("LST", NOISE), True, 20)
    assert found == [
        "Orchard: only 20 months in common; a correlation needs about 36 to mean much."
    ]
    short = guardrails.lags("Orchard", ("NDVI", NOISE[:30]), [], True)
    assert "only 30 months of NDVI" in short[0]


def test_a_driver_larger_than_the_area_is_carried_to_the_lag_test():
    warning = "This area (0.64 km²) is smaller than one 1 km pixel of LST, so its values include the surroundings."
    found = guardrails.lags("Orchard", ("NDVI", NOISE), [("LST", NOISE, [warning])], True)
    assert found == [f"Orchard: LST: {warning}"]


def test_a_short_record_is_flagged_for_decomposition():
    assert guardrails.decomposition("Field", "NDVI", 2.5)[0].startswith(
        "Field, NDVI: only 2.5 years"
    )
    assert guardrails.decomposition("Field", "NDVI", 20) == []


def fitted(name, rmse, sd=0.0, rolling=()):
    return {
        "name": name,
        "test": {"RMSE": rmse},
        "seeds": {"runs": 20 if sd else 1, "RMSE_sd": sd},
        "rolling": [{"RMSE": r} for r in rolling],
    }


def forecast(models, climatology=0.07, months=36):
    return {
        "models": models,
        "baselines": {"persistence": {"RMSE": 0.1}, "climatology": {"RMSE": climatology}},
        "observed": [0.0] * months,
    }


def test_a_forecast_that_does_not_beat_climatology_is_flagged():
    found = guardrails.models(
        "Corn", forecast([fitted("Ridge", 0.08), fitted("XGBoost", 0.09, 0.001)])
    )
    assert found[0].startswith("Corn: no model beats climatology (RMSE 0.0700)")


def test_a_lead_within_noise_or_within_the_spread_of_windows_is_flagged():
    close = forecast([fitted("XGBoost", 0.050, 0.001), fitted("RandomForest", 0.051, 0.001)])
    assert any("neither is better" in c for c in guardrails.models("Orchard", close))
    windows = forecast(
        [
            fitted("XGBoost", 0.050, 0.0005, rolling=[0.04, 0.05, 0.06]),
            fitted("RandomForest", 0.055, 0.0005, rolling=[0.045, 0.05, 0.055]),
        ]
    )
    found = guardrails.models("Orchard", windows)
    assert any("depends on the test period" in c for c in found)
    assert not any("neither is better" in c for c in found)


def test_a_clear_skilful_forecast_has_no_caution():
    clear = forecast(
        [
            fitted("XGBoost", 0.040, 0.0005, rolling=[0.040, 0.041]),
            fitted("Ridge", 0.060, rolling=[0.06, 0.061]),
        ]
    )
    assert guardrails.models("Orchard", clear) == []
    assert (
        "only 12 test months"
        in guardrails.models("Orchard", forecast([fitted("Ridge", 0.04)], months=12))[0]
    )
