import json

import ee
import pytest

from engine.catalogue import CATALOGUE, get_variable
from engine.earth_engine import connect


def test_every_variable_is_described_and_explained():
    assert len(CATALOGUE) == 14
    for variable in CATALOGUE.values():
        assert variable.product and variable.licence and variable.citation, variable.key
        assert variable.group and variable.learn, variable.key
        assert variable.learn.what and variable.learn.reading and variable.learn.uses


def test_eight_day_totals_are_shown_per_day():
    # GPP is stored as kg C/m² per 8 days, scaled by 0.0001
    assert 400 * get_variable("gpp").scale == pytest.approx(5.0)  # g C/m² per day


def test_metadata_is_plain_json():
    for variable in CATALOGUE.values():
        json.dumps(variable.to_dict())


def test_lst_is_converted_to_celsius():
    lst = get_variable("lst")
    assert 15000 * lst.scale + lst.offset == pytest.approx(26.85)


def test_unknown_variable_names_the_choices():
    with pytest.raises(KeyError, match="ndvi, savi, evi"):
        get_variable("rainfall")


@pytest.mark.live
def test_live_every_band_exists():
    connect()
    for variable in CATALOGUE.values():
        bands = ee.ImageCollection(variable.collection).first().bandNames().getInfo()
        names = [variable.band.format(scale=s) for s in variable.scales] or [variable.band]
        computed = {  # from reflectances
            "savi": ["sur_refl_b01", "sur_refl_b02"],
            "ndmi": ["sur_refl_b02", "sur_refl_b06", "StateQA"],
            "nbr": ["sur_refl_b02", "sur_refl_b07", "SummaryQA"],
        }
        names = computed.get(variable.key, names)
        assert set(names) <= set(bands), variable.key
