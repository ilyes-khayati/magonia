import numpy as np
import pandas as pd
import pytest

from engine.decompose import split
from engine.leakage import LeakageError, audit, causal_parts

MONTHS = pd.date_range("2000-01-01", periods=300, freq="MS")


def test_a_causal_part_uses_no_later_month():
    rng = np.random.default_rng(1)
    values = rng.normal(size=120)
    trend, _ = causal_parts(values)
    changed = values.copy()
    changed[100:] += 50  # a jump later on must not move the parts before it
    later, _ = causal_parts(changed)
    np.testing.assert_allclose(trend[:100], later[:100])
    # while decomposing the whole record moves them
    assert not np.allclose(split(values, 4)[0][:100], split(changed, 4)[0][:100])


def test_on_noise_whole_record_trend_skill_is_an_artefact():
    rng = np.random.default_rng(2)
    found = audit(pd.Series(rng.normal(size=300), MONTHS), "NDVI", "Test")
    assert found.placebo["whole"] > 0.9
    assert found.placebo["causal"] < found.placebo["whole"] - 0.3
    assert "on white noise" in found.summary[1]


def test_a_seasonal_series_is_audited_against_its_own_lags():
    rng = np.random.default_rng(3)
    t = np.arange(300)
    values = 0.5 + 0.2 * np.sin(2 * np.pi * t / 12) + 0.03 * rng.normal(size=300)
    found = audit(pd.Series(values, MONTHS), "NDVI", "Orchard")
    assert {r["model"] for r in found.rows} == {"Ridge", "RandomForest", "XGBoost"}
    assert len(found.dates) == 36 and len(found.whole) == len(found.causal) == 36
    assert found.rows[0]["raw"] < found.baselines["persistence"]


def test_short_records_are_refused():
    with pytest.raises(LeakageError, match="needs 96"):
        audit(pd.Series(np.arange(60.0), MONTHS[:60]), "NDVI", "Orchard")
