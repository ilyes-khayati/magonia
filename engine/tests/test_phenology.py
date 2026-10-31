import numpy as np
import pandas as pd
import pytest

from engine.phenology import PhenologyError, phenology


def points(peak_doy=70, amplitude=0.4, years=6, start="2010-01-01"):
    dates = pd.date_range(start, periods=23 * years, freq="16D")
    values = 0.3 + amplitude * np.exp(
        -0.5 * (((dates.dayofyear - peak_doy + 182) % 365 - 182) / 40) ** 2
    )
    return [
        {"date": f"{d:%Y-%m-%d}", "value": float(v), "masked": False, "filled": False}
        for d, v in zip(dates, values)
    ]


def test_a_season_that_crosses_the_new_year_is_found_around_its_peak():
    found = phenology("Orchard", "NDVI", "ndvi", points(peak_doy=20))
    assert len(found.seasons) >= 4
    for season in found.seasons:
        assert pd.Timestamp(season.start) < pd.Timestamp(season.peak) < pd.Timestamp(season.end)
        assert (
            abs(pd.Timestamp(season.peak).dayofyear - 20) < 12
            or pd.Timestamp(season.peak).dayofyear > 355
        )
        assert 100 < season.length < 200
        assert season.amplitude == pytest.approx(0.4, abs=0.05)
    assert "the growing season starts around" in found.summary[0]
    assert found.cautions == []


def test_a_weak_cycle_is_cautioned_and_other_variables_refused():
    weak = phenology("Desert", "NDVI", "ndvi", points(amplitude=0.04))
    assert "the yearly cycle is weak" in weak.cautions[0]
    with pytest.raises(PhenologyError, match="measure of vegetation"):
        phenology("Desert", "LST", "lst", points())
    with pytest.raises(PhenologyError):
        phenology("Desert", "NDVI", "ndvi", points(years=1))


def test_savi_has_seasons_like_ndvi():
    assert phenology("Orchard", "SAVI", "savi", points()).seasons
