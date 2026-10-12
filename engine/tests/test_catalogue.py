import json

import ee
import pytest

from engine.catalogue import CATALOGUE, get_variable
from engine.earth_engine import connect


def test_ndvi_lst_and_spei_are_described():
    assert set(CATALOGUE) == {"ndvi", "lst", "spei"}
    for variable in CATALOGUE.values():
        assert variable.product and variable.licence and variable.citation


def test_metadata_is_plain_json():
    for variable in CATALOGUE.values():
        json.dumps(variable.to_dict())


def test_lst_is_converted_to_celsius():
    lst = get_variable("lst")
    assert 15000 * lst.scale + lst.offset == pytest.approx(26.85)


def test_unknown_variable_names_the_choices():
    with pytest.raises(KeyError, match="ndvi, lst, spei"):
        get_variable("rainfall")


@pytest.mark.live
def test_live_every_band_exists():
    connect()
    for variable in CATALOGUE.values():
        bands = ee.ImageCollection(variable.collection).first().bandNames().getInfo()
        names = [variable.band.format(scale=s) for s in variable.scales] or [variable.band]
        assert set(names) <= set(bands), variable.key
