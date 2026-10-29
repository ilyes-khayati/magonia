import math

from engine.trend import trend


def points(values, start_year=2001):
    return [
        {
            "date": f"{start_year + i // 12}-{i % 12 + 1:02d}-01",
            "value": v,
            "masked": False,
            "filled": False,
        }
        for i, v in enumerate(values)
    ]


def test_a_steady_rise_is_found_and_tested():
    rising = [0.4 + 0.01 * (i // 12) + 0.2 * math.sin(2 * math.pi * i / 12) for i in range(12 * 15)]
    found = trend("Orchard", "NDVI", "ndvi", "", points(rising))
    assert round(found.slope, 3) == 0.1  # 0.01 a year is 0.1 a decade
    assert found.p < 0.001 and len(found.years) == 15
    assert found.summary[0].startswith(
        "Orchard, NDVI: annual means rising by +0.100 per decade (Sen's slope) over 15 years (2001 to 2015); statistically significant"
    )
    assert any("consecutive years are correlated" in c for c in found.cautions)


def test_a_flat_noisy_series_is_not_significant():
    flat = [0.5 + 0.05 * math.sin(i * 1.7) for i in range(12 * 12)]
    found = trend("Orchard", "NDVI", "ndvi", "", points(flat))
    assert found.p > 0.05 and "not statistically significant" in found.summary[0]


def test_winters_missing_every_year_are_left_out_of_the_annual_means():
    snowy = points([0.3 + 0.01 * (i // 12) for i in range(12 * 10)])
    snowy = [p for p in snowy if p["date"][5:7] not in ("01", "02", "12")]
    found = trend("Field", "NDVI", "ndvi", "", snowy)
    assert found.months == ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
    assert "(over Mar, Apr" in found.summary[0]


def test_short_records_are_cautioned_or_refused():
    assert trend("Field", "NDVI", "ndvi", "", points([0.5] * 24)).slope is None
    short = trend(
        "Field", "NDVI", "ndvi", "", points([0.3 + 0.01 * (i // 12) for i in range(12 * 5)])
    )
    assert "only 5 complete years" in short.cautions[0]
