"""Long-term change in a series, tested (requirement ANA-04).

Each year is summarised by its mean over the calendar months observed in most years, so that
snowy or cloudy months missing every winter do not bias the comparison. The trend is the
Theil–Sen slope of those annual means, robust to a few odd years, and its significance the
Mann–Kendall test. Mann–Kendall assumes the years are independent; when consecutive annual
means are correlated it reports trends too often, which the cautions say.
"""

from dataclasses import asdict, dataclass, field
from statistics import median

import numpy as np

from engine.facts import complete_years, fmt, mann_kendall, monthly, sen_slope, usual_months

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MIN_YEARS = 8  # fewer years leave the test with almost no power
SERIAL = 0.3  # lag-1 autocorrelation of annual means beyond which p is too optimistic


@dataclass
class Trend:
    years: dict[int, float]  # annual mean over the usual months
    months: list[str]  # the calendar months the annual means are taken over
    slope: float | None  # per decade, Theil–Sen
    intercept: float | None  # so that value = intercept + slope / 10 * (year - first year)
    p: float | None  # Mann–Kendall, two-sided
    change: float | None  # slope times the number of decades covered
    summary: list[str]
    cautions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["years"] = {str(k): v for k, v in self.years.items()}
        return d


def trend(area: str, title: str, key: str, units: str, points: list[dict]) -> Trend:
    series = monthly(points)
    years = complete_years(series)
    months = sorted(usual_months(series))  # calendar months, 0 for January
    calendar = [MONTHS[c] for c in months]
    who = f"{area}, {title}"
    unit = f" {units}" if units else ""
    over = (
        "" if len(months) == 12 else f" (over {', '.join(calendar)}, the months seen in most years)"
    )
    if len(years) < 3:
        return Trend(
            years,
            calendar,
            None,
            None,
            None,
            None,
            [f"{who}: fewer than 3 complete years{over}; no trend can be tested."],
        )

    order = sorted(years)
    values = [years[y] for y in order]
    slope_year = sen_slope(order, values)
    intercept = median(v - slope_year * (y - order[0]) for y, v in zip(order, values))
    p = mann_kendall(values)
    span = order[-1] - order[0]
    change = slope_year * span
    verdict = "statistically significant" if p < 0.05 else "not statistically significant"
    digits = 2 if key == "lst" else 3
    shown = round(slope_year * 10, digits)
    direction = "rising" if shown > 0 else "falling" if shown < 0 else "about flat, changing"
    first, last = values[0], values[-1]
    rate = (
        f"{who}: annual means{over} {direction} by {slope_year * 10:+.{digits}f}{unit} per decade "
        f"(Sen's slope) over {len(order)} years ({order[0]} to {order[-1]}); {verdict} "
        f"(Mann-Kendall p = {p:.2f})."
    )
    moved = (
        f"{who}: over the period the trend line moved by {change:+.{digits}f}{unit}; the first "
        f"year's mean was {fmt(first, key)} and the last's {fmt(last, key)}."
    )
    summary = [rate, moved]
    cautions = []
    if len(order) < MIN_YEARS:
        cautions.append(
            f"{who}: only {len(order)} complete years; a trend test needs about {MIN_YEARS} to "
            "find anything but a strong trend."
        )
    if len(order) >= 4:
        r1 = float(np.corrcoef(values[:-1], values[1:])[0, 1])
        if r1 > SERIAL and p < 0.05:
            cautions.append(
                f"{who}: consecutive years are correlated (r = {r1:.2f}), which makes the "
                "Mann-Kendall test report significance too often; read p as optimistic."
            )
    return Trend(years, calendar, slope_year * 10, intercept, p, change, summary, cautions)
