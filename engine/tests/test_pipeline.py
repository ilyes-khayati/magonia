import json

import pytest

from engine.pipeline import Request, run

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[8.55, 36.50], [8.56, 36.50], [8.56, 36.51], [8.55, 36.51], [8.55, 36.50]]],
}


def fake_fetch(key, geometry, start, end, masking, scale):
    values = [5000, None, 7000, 6000]
    return [
        {"properties": {"date": f"2023-0{i + 1}-01", "value": v, "sd": 100, "n_pixels": 20}}
        if v is not None
        else {"properties": {"date": f"2023-0{i + 1}-01", "n_pixels": 0}}
        for i, v in enumerate(values)
    ]


def test_steps_are_recorded():
    result = run(Request("ndvi", SQUARE, "2023-01-01", "2023-05-01"), fetch=fake_fetch)
    record = result.provenance
    assert record["variable"]["product"] == "MODIS Terra MOD13Q1 v6.1"
    assert record["area"]["area_km2"] == pytest.approx(0.995, abs=0.01)
    steps = {step["step"]: step for step in record["steps"]}
    assert steps["extract"]["dates"] == 4
    assert steps["quality"]["dates_without_data"] == 1
    assert steps["fill gaps"]["filled"] == 1
    assert result.table["filled"].tolist() == [False, True, False, False]


def test_provenance_is_plain_json():
    record = run(Request("ndvi", SQUARE, "2023-01-01", "2023-05-01"), fetch=fake_fetch).provenance
    assert json.loads(json.dumps(record)) == record


def test_identical_requests_give_identical_provenance_and_values():
    request = Request("ndvi", SQUARE, "2023-01-01", "2023-05-01", resolution="monthly")
    first, second = run(request, fetch=fake_fetch), run(request, fetch=fake_fetch)
    assert first.provenance == second.provenance
    assert first.table.equals(second.table)


def test_any_change_gives_a_new_id():
    base = run(Request("ndvi", SQUARE, "2023-01-01", "2023-05-01"), fetch=fake_fetch)
    no_filling = run(
        Request("ndvi", SQUARE, "2023-01-01", "2023-05-01", max_gap=0), fetch=fake_fetch
    )
    assert base.provenance["id"] != no_filling.provenance["id"]
    assert no_filling.provenance["steps"][-1] == {"step": "fill gaps", "method": "off"}


def test_invalid_area_fails_before_earth_engine():
    def must_not_run(*args):
        raise AssertionError("Earth Engine was called")

    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    with pytest.raises(ValueError, match="Self-intersection"):
        run(Request("ndvi", bowtie, "2023-01-01", "2023-05-01"), fetch=must_not_run)
