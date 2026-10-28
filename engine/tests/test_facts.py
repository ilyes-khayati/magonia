import math
import random

from engine.facts import (
    Series,
    View,
    lag_correlation,
    mann_kendall,
    sen_slope,
    series_facts,
)


def points(values, start_year=2020, masked=(), filled=()):
    """Monthly points from January of start_year, as the API returns them."""
    return [
        {
            "date": f"{start_year + i // 12}-{i % 12 + 1:02d}-01",
            "value": v,
            "masked": i in masked or i in filled,
            "filled": i in filled,
        }
        for i, v in enumerate(values)
    ]


def seasonal(years, base=0.3, step=0.0):
    """A cycle peaking in August, rising by step each year."""
    return [
        base + y * step + 0.4 * max(0.0, math.cos((m - 7) / 2.5))
        for y in range(years)
        for m in range(12)
    ]


def ndvi(area, values, **kwargs):
    return Series(area, "ndvi", "NDVI", "", points(values, **kwargs))


def texts(facts):
    return " | ".join(f.text for f in facts)


def test_the_average_year_peaks_and_dips_where_the_chart_does():
    facts = series_facts(ndvi("Orchard", seasonal(3)))
    assert "peaks in Aug (0.70)" in texts(facts)
    assert "lowest in Jan" in texts(facts)
    assert all(f.card == "NDVI chart" for f in facts)


def test_filled_and_masked_values_are_left_out():
    values = seasonal(2)
    values[3] = 5.0  # an absurd value, but filled
    facts = series_facts(ndvi("Orchard", values, filled={3}))
    assert "5.00" not in texts(facts)
    assert "23 observations" in texts(facts) and "1 gaps filled" in texts(facts)


def test_a_steady_rise_is_a_significant_trend():
    facts = series_facts(ndvi("Orchard", seasonal(8, step=0.01)))
    trend = next(f for f in facts if "trend" in f.text)
    assert "+0.100 per decade" in trend.text and "statistically significant" in trend.text
    assert "not statistically" not in trend.text


def test_trend_helpers():
    # one wild year moves a least-squares line, not the median of the pairwise slopes
    assert sen_slope([2000, 2001, 2002, 2003, 2004], [1, 2, 3, 4, 100]) == 1
    assert mann_kendall([1, 2, 3, 4, 5, 6, 7, 8]) < 0.01
    assert mann_kendall([1, 1, 1, 1, 1]) == 1.0


def test_no_trend_is_claimed_from_too_few_years():
    assert not any("trend" in f.text for f in series_facts(ndvi("Orchard", seasonal(4))))


def test_spei_is_described_by_its_droughts():
    s = Series("Orchard", "spei", "SPEI-12", "", points([0.5, -1.2, -2.3, 0.1] * 6))
    text = texts(series_facts(s))
    assert "driest month 2020-03 (-2.30, extreme drought)" in text
    assert "12 of 24 months (50%) at or below -1" in text
    assert "peaks" not in text


def test_a_lagged_driver_is_found_at_its_lag():
    rng = random.Random(1)
    noise = [rng.gauss(0, 1) for _ in range(62)]
    driver = points(noise[2:] + [0, 0])  # driver leads: response[m] = driver[m - 2]
    response = points([0, 0] + noise[2:])
    lags = lag_correlation(response[2:], driver[:-2])
    best = max(lags, key=lambda lag: abs(lag.r))
    assert best.lag == 2 and round(best.r, 6) == 1


def correlated_view(deseasonalise=True):
    rng = random.Random(2)
    lst = [20 + 10 * math.sin(i / 1.9) + rng.gauss(0, 1) for i in range(48)]
    green = [0.9 - 0.02 * t + rng.gauss(0, 0.01) for t in lst]
    return View(
        context=["Areas: Orchard (0.64 km²)."],
        series=[ndvi("Orchard", green), Series("Orchard", "lst", "LST", "°C", points(lst))],
        charts=["ndvi"],
        analyses=[
            {
                "id": 1,
                "kind": "correlation",
                "response": "ndvi",
                "driver": "lst",
                "deseasonalise": deseasonalise,
            }
        ],
    )


def test_correlation_facts_name_their_card_and_direction():
    facts = correlated_view().facts()
    fact = next(f for f in facts if f.card.startswith("Correlation 1"))
    assert fact.card == "Correlation 1: NDVI and LST"
    assert "same month" in fact.text and "higher LST goes with lower NDVI" in fact.text
    assert fact.values[0] < -0.6


def test_the_sheet_groups_facts_under_their_cards():
    sheet = correlated_view().sheet()
    assert sheet.startswith("What is open in Magonia now")
    assert "- Areas: Orchard (0.64 km²)." in sheet
    assert sheet.index("[NDVI chart]") < sheet.index("[Correlation 1: NDVI and LST]")
    # LST is fetched for the analysis but not charted, so it has no card of its own
    assert "[LST chart]" not in sheet


def test_two_areas_are_compared_like_the_summary_card():
    view = View(
        [], [ndvi("Orchard", seasonal(2)), ndvi("Field", seasonal(2, base=0.1))], ["ndvi"], []
    )
    summary = next(f for f in view.facts() if f.card == "Summary")
    assert "Orchard is higher than Field by 0.20" in summary.text


def test_an_empty_view_says_so():
    assert "No charts or analyses are open yet." in View([], [], [], []).sheet()


def test_reading_a_year_or_every_year():
    view = correlated_view()
    year = view.read("orchard", "NDVI", 2021)
    assert year.startswith("Orchard, NDVI, monthly means in 2021: Jan ")
    assert year.count(",") >= 12
    assert "annual means: 2020 " in view.read("Orchard", "ndvi")
    assert "°C" in view.read("Orchard", "lst", 2020)
    assert view.read("Vineyard", "ndvi").startswith(
        "No series for Vineyard ndvi. Open now: Orchard NDVI"
    )


def test_years_are_compared_over_their_usual_months_when_winter_is_always_missing():
    winter = {i for i in range(72) if i % 12 in (0, 1, 11)}  # snow every Dec, Jan and Feb
    facts = series_facts(ndvi("Field", seasonal(6, step=0.01), masked=winter))
    text = texts(facts)
    assert (
        "annual means over Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov: of the 6 complete years"
        in text
    )
    assert "+0.100 per decade" in text


def test_a_decomposition_reports_the_trend_and_the_seasonal_share():
    rise = [0.3 + 0.002 * i + 0.3 * math.sin(i * 2 * math.pi / 12) for i in range(72)]
    native = Series("Field", "spei", "SPEI-3", "", points(rise), "native")
    monthly = Series("Field", "spei", "SPEI-3", "", points([0.0] * 72))
    view = View([], [monthly, native], [], [{"id": 1, "kind": "decomposition", "variable": "spei"}])
    facts = [f for f in view.facts() if f.card == "Decomposition 1: SPEI-3"]
    text = texts(facts)
    # a rise of 0.024 a year, softened at the ends by the mirrored padding
    assert text.startswith("Field, SPEI-3: the trend went from 0.36 (2020 mean) to 0.39 (2025 mean)")
    assert "the seasonal part carries" in text and "not a forecast" in text
    # the charts keep reading the series at their own step
    assert view.read("Field", "spei", 2020).endswith("Dec 0.00.")


def test_a_decomposition_of_too_short_a_series_says_why():
    short = Series("Field", "spei", "SPEI-3", "", points([0.1] * 24), "native")
    view = View([], [short], [], [{"id": 1, "kind": "decomposition", "variable": "spei"}])
    assert "three years" in texts(view.facts())
