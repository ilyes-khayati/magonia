"""Facts about the researcher's own data, computed by code for the assistant to discuss.

The assistant never reads raw series. It reads these sentences, each tied to the card on
screen that it describes, computed with the same definitions as the interface
(web/src/stats.ts and web/src/correlation.ts) so that the assistant and the screen agree.
"""

import math
from dataclasses import dataclass, field
from statistics import fmean, median, pstdev

import pandas as pd

from engine import guardrails
from engine.decompose import DecompositionError, decompose
from engine.lags import explore

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MIN_PAIRS = 12  # fewer months in common and a correlation is not computed
MIN_TREND_YEARS = 5


@dataclass
class Series:
    """One variable over one area, as the interface received it."""

    area: str
    key: str  # ndvi, lst, spei
    title: str  # as its card shows it, e.g. "SPEI-12"
    units: str
    points: list[dict]  # date, value, masked, filled, ...
    resolution: str = "monthly"  # native, monthly or seasonal
    warnings: list[str] = field(default_factory=list)  # the product's own, e.g. pixel size


@dataclass
class Fact:
    card: str  # the card on screen it describes, e.g. "NDVI chart"
    text: str
    values: list[float] = field(default_factory=list)  # its numbers, for checking answers


def fmt(value: float, key: str) -> str:
    return f"{value:.1f}" if key == "lst" else f"{value:.2f}"


def month_of(date: str) -> int:
    """Months since year 0, so that consecutive months differ by one."""
    return int(date[:4]) * 12 + int(date[5:7]) - 1


def label(month: int) -> str:
    return f"{month // 12}-{month % 12 + 1:02d}"


def observed(points: list[dict]) -> list[tuple[str, float]]:
    """Real observations only: filled and masked values are left out of every statistic."""
    return [(p["date"], p["value"]) for p in points if p["value"] is not None and not p["masked"]]


def monthly(points: list[dict]) -> dict[int, float]:
    """Observations averaged by calendar month, since products have different dates."""
    by_month: dict[int, list[float]] = {}
    for p in points:
        if p["value"] is not None and not p["masked"] and not p.get("filled"):
            by_month.setdefault(month_of(p["date"]), []).append(p["value"])
    return {m: fmean(values) for m, values in sorted(by_month.items())}


def climatology(series: dict[int, float]) -> dict[int, float]:
    """The average of each calendar month (0 = January) across years."""
    by_calendar: dict[int, list[float]] = {}
    for m, v in series.items():
        by_calendar.setdefault(m % 12, []).append(v)
    return {c: fmean(values) for c, values in by_calendar.items()}


def anomalies(series: dict[int, float]) -> dict[int, float]:
    """Each value minus the average of its calendar month: the year-to-year variation."""
    normal = climatology(series)
    return {m: v - normal[m % 12] for m, v in series.items()}


def pearson(xs: list[float], ys: list[float]) -> float:
    mx, my = fmean(xs), fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else math.nan


def usual_months(series: dict[int, float]) -> set[int]:
    """The calendar months observed in at least half of the years. Snow or persistent cloud
    can leave some months empty every year; years are compared over the others."""
    by_year: dict[int, set[int]] = {}
    for m in series:
        by_year.setdefault(m // 12, set()).add(m % 12)
    count = {c: sum(c in months for months in by_year.values()) for c in range(12)}
    return {c for c, n in count.items() if n and n >= len(by_year) / 2}


def complete_years(series: dict[int, float]) -> dict[int, float]:
    """Annual means over the usual months, for the years in which all of them were observed."""
    usual = usual_months(series)
    by_year: dict[int, dict[int, float]] = {}
    for m, v in series.items():
        if m % 12 in usual:
            by_year.setdefault(m // 12, {})[m % 12] = v
    return {
        year: fmean(values.values())
        for year, values in by_year.items()
        if usual and set(values) == usual
    }


def mann_kendall(xs: list[float]) -> float:
    """Two-sided p-value of the Mann-Kendall trend test (normal approximation, no ties)."""
    n = len(xs)
    s = sum((xs[j] > xs[i]) - (xs[j] < xs[i]) for i in range(n) for j in range(i + 1, n))
    if s == 0:
        return 1.0
    z = (s - math.copysign(1, s)) / math.sqrt(n * (n - 1) * (2 * n + 5) / 18)
    return math.erfc(abs(z) / math.sqrt(2))


def sen_slope(years: list[int], xs: list[float]) -> float:
    """Median of the slopes between every pair of years (Theil–Sen), per year."""
    n = len(xs)
    return median(
        (xs[j] - xs[i]) / (years[j] - years[i]) for i in range(n) for j in range(i + 1, n)
    )


def drought_class(spei: float) -> str:
    if spei <= -2:
        return "extreme drought"
    if spei <= -1.5:
        return "severe drought"
    if spei <= -1:
        return "moderate drought"
    return "no drought"


def series_facts(s: Series) -> list[Fact]:
    """What the card of one variable over one area shows, in sentences."""
    card = f"{s.title} chart"
    who = f"{s.area}, {s.title}"
    unit = f" {s.units}" if s.units else ""
    obs = observed(s.points)
    if not obs:
        return [Fact(card, f"{who}: no observations in this period.")]

    def say(text: str, *values: float) -> Fact:
        return Fact(card, f"{who}: {text}", [round(v, 4) for v in values])

    filled = sum(1 for p in s.points if p.get("filled"))
    facts = [
        say(
            f"{len(obs)} observations from {obs[0][0][:7]} to {obs[-1][0][:7]}; {filled} gaps filled "
            "by interpolation, left out of these statistics."
        )
    ]
    values = [v for _, v in obs]
    low = min(obs, key=lambda o: o[1])
    high = max(obs, key=lambda o: o[1])
    months = monthly(s.points)
    normal = climatology(months)

    if s.key == "spei":
        dry = sum(v <= -1 for v in values)
        facts.append(
            say(
                f"driest month {low[0][:7]} ({fmt(low[1], s.key)}, {drought_class(low[1])}); wettest "
                f"{high[0][:7]} ({fmt(high[1], s.key)}); {dry} of {len(values)} months "
                f"({100 * dry / len(values):.0f}%) at or below -1, moderate drought or worse.",
                low[1],
                high[1],
            )
        )
    else:
        mean, sd = fmean(values), pstdev(values)
        facts.append(
            say(
                f"mean {fmt(mean, s.key)}{unit} (standard deviation {fmt(sd, s.key)}); lowest "
                f"{fmt(low[1], s.key)} in {low[0][:7]}, highest {fmt(high[1], s.key)} in {high[0][:7]}.",
                mean,
                sd,
                low[1],
                high[1],
            )
        )
        # the average year, as the seasonal-cycle chart draws it
        by_calendar: dict[int, list[float]] = {}
        for date, v in obs:
            by_calendar.setdefault(int(date[5:7]) - 1, []).append(v)
        cycle = {c: fmean(vs) for c, vs in by_calendar.items()}
        peak = max(cycle, key=cycle.get)
        trough = min(cycle, key=cycle.get)
        facts.append(
            say(
                f"in an average year it peaks in {MONTHS[peak]} ({fmt(cycle[peak], s.key)}{unit}) and is "
                f"lowest in {MONTHS[trough]} ({fmt(cycle[trough], s.key)}{unit}).",
                cycle[peak],
                cycle[trough],
            )
        )

    years = complete_years(months)
    if len(years) >= 2:
        best = max(years, key=years.get)
        worst = min(years, key=years.get)
        usual = usual_months(months)
        over = "" if len(usual) == 12 else f" over {', '.join(MONTHS[c] for c in sorted(usual))}"
        facts.append(
            say(
                f"annual means{over}: of the {len(years)} complete years ({min(years)} to "
                f"{max(years)}), {best} had the "
                f"highest mean ({fmt(years[best], s.key)}) and {worst} the lowest "
                f"({fmt(years[worst], s.key)}).",
                years[best],
                years[worst],
            )
        )
    if len(years) >= MIN_TREND_YEARS:
        order = sorted(years)
        trend = sen_slope(order, [years[y] for y in order]) * 10
        p = mann_kendall([years[y] for y in order])
        verdict = "statistically significant" if p < 0.05 else "not statistically significant"
        digits = 2 if s.key == "lst" else 3
        facts.append(
            say(
                f"trend in the annual means {trend:+.{digits}f}{unit} per decade (Sen's slope), "
                f"{verdict} (Mann-Kendall p = {p:.2f}).",
                trend,
                p,
            )
        )

    last = max(months)
    if s.key == "spei":
        facts.append(
            say(
                f"latest month {label(last)}: {fmt(months[last], s.key)} ({drought_class(months[last])}).",
                months[last],
            )
        )
    elif len(months) > 12:
        gaps = anomalies(months)
        odd = max(gaps, key=lambda m: abs(gaps[m]))
        latest = gaps[last]
        facts.append(
            say(
                f"most unusual month {label(odd)}, {fmt(abs(gaps[odd]), s.key)}{unit} "
                f"{'above' if gaps[odd] > 0 else 'below'} the usual {MONTHS[odd % 12]}; latest month "
                f"{label(last)} at {fmt(months[last], s.key)}{unit}, {fmt(abs(latest), s.key)}{unit} "
                f"{'above' if latest > 0 else 'below'} the usual {MONTHS[last % 12]} "
                f"({fmt(normal[last % 12], s.key)}{unit}).",
                abs(gaps[odd]),
                months[last],
                abs(latest),
                normal[last % 12],
            )
        )
    return facts


def comparison_fact(a: Series, b: Series) -> Fact | None:
    """The month in which two areas differ most in an average year, as the summary card says."""

    def cycle(s: Series) -> dict[int, float]:
        by_calendar: dict[int, list[float]] = {}
        for date, v in observed(s.points):
            by_calendar.setdefault(int(date[5:7]) - 1, []).append(v)
        return {c: fmean(vs) for c, vs in by_calendar.items()}

    ca, cb = cycle(a), cycle(b)
    gaps = {m: ca[m] - cb[m] for m in ca if m in cb}
    if not gaps:
        return None
    widest = max(gaps, key=lambda m: abs(gaps[m]))
    higher, lower = (a.area, b.area) if gaps[widest] > 0 else (b.area, a.area)
    unit = f" {a.units}" if a.units else ""
    return Fact(
        "Summary",
        f"{a.title}: the two areas differ most in {MONTHS[widest]}, when {higher} is higher than "
        f"{lower} by {fmt(abs(gaps[widest]), a.key)}{unit}.",
        [round(abs(gaps[widest]), 4)],
    )


@dataclass
class Lag:
    lag: int
    r: float
    n: int
    band: float  # approximate 95% limit for no correlation, ±1.96/√n


def lag_correlation(
    response: list[dict], driver: list[dict], max_lag: int = 12, deseasonalise: bool = True
) -> list[Lag]:
    """Correlation between the response and the driver *lag* months earlier, for each lag."""
    a, b = monthly(response), monthly(driver)
    if deseasonalise:
        a, b = anomalies(a), anomalies(b)
    lags = []
    for lag in range(max_lag + 1):
        pairs = [(b[m - lag], v) for m, v in a.items() if m - lag in b]
        if len(pairs) < MIN_PAIRS:
            continue
        r = pearson([x for x, _ in pairs], [y for _, y in pairs])
        if not math.isnan(r):
            lags.append(Lag(lag, r, len(pairs), 1.96 / math.sqrt(len(pairs))))
    return lags


def correlation_fact(card: str, response: Series, driver: Series, deseasonalise: bool) -> Fact:
    lags = lag_correlation(response.points, driver.points, deseasonalise=deseasonalise)
    who = f"{response.area}"
    if not lags:
        return Fact(
            card,
            f"{who}: no correlation can be computed (fewer than {MIN_PAIRS} months in common).",
        )
    best = max(lags, key=lambda lag: abs(lag.r))
    what = "anomalies" if deseasonalise else "values (seasonal cycle kept)"
    when = (
        "the same month"
        if best.lag == 0
        else f"{best.lag} month{'s' if best.lag > 1 else ''} earlier"
    )
    stats = f"r = {best.r:.2f}, {best.n} months, chance band ±{best.band:.2f}"
    values = [round(best.r, 4), best.n, round(best.band, 4)]
    if abs(best.r) < best.band:
        text = (
            f"{who}: no lag of {driver.title} stands out from chance for {response.title} {what} "
            f"(strongest at {when}: {stats})."
        )
    else:
        direction = "higher" if best.r > 0 else "lower"
        strength = "weak" if abs(best.r) < 0.3 else "moderate" if abs(best.r) < 0.6 else "strong"
        text = (
            f"{who}: {response.title} {what} are most closely linked to {driver.title} from {when} "
            f"({stats}; {strength}): higher {driver.title} goes with {direction} {response.title}."
        )
    same = next((lag for lag in lags if lag.lag == 0), None)
    if same and best.lag != 0:
        text += f" In the same month, r = {same.r:.2f}."
        values.append(round(same.r, 4))
    return Fact(card, text, values)


def decomposition_facts(card: str, s: Series) -> list[Fact]:
    """What the decomposition card shows: how the trend moved and how much is seasonal."""
    who = f"{s.area}, {s.title}"
    frame = pd.DataFrame(s.points)
    values = frame["value"].where(~frame["masked"] | frame["filled"])
    try:
        result = decompose(frame["date"], values, s.key)
    except DecompositionError as exc:
        return [Fact(card, f"{who}: {exc}")]
    m = result.monthly.dropna()
    cautions = caution_facts(card, guardrails.decomposition(s.area, s.title, len(m) / 12))
    trend = m.set_index("date")["trend"]
    years = trend.groupby(trend.index.year).mean()
    first, last = years.index[0], years.index[-1]
    low, high = trend.idxmin(), trend.idxmax()
    var_t, var_s = m["trend"].var(), m["seasonal"].var()
    share = 100 * var_s / (var_t + var_s)
    swing = m.groupby(m["date"].dt.year)["seasonal"].agg(lambda x: x.max() - x.min()).mean()
    unit = f" {s.units}" if s.units else ""
    return [
        Fact(
            card,
            f"{who}: the trend went from {fmt(years.iloc[0], s.key)}{unit} ({first} mean) to "
            f"{fmt(years.iloc[-1], s.key)}{unit} ({last} mean); lowest {fmt(trend[low], s.key)} in "
            f"{low:%Y-%m}, highest {fmt(trend[high], s.key)} in {high:%Y-%m}.",
            [
                round(years.iloc[0], 4),
                round(years.iloc[-1], 4),
                round(trend[low], 4),
                round(trend[high], 4),
            ],
        ),
        Fact(
            card,
            f"{who}: the seasonal part carries {share:.0f}% of the variation and the trend "
            f"{100 - share:.0f}%; the seasonal part swings by {fmt(swing, s.key)}{unit} within a "
            "year on average.",
            [round(share, 4), round(swing, 4)],
        ),
        Fact(
            card,
            f"{who}: discrete Meyer wavelet at level {result.level} on {s.title}'s "
            f"{result.cadence_days:.0f}-day steps, so the trend keeps cycles longer than about "
            f"{result.semi_period_days:.0f} days; {result.interpolated} empty dates were filled by "
            "straight lines first. The filter uses later data too, so the trend describes the "
            "past and is not a forecast.",
        ),
    ] + cautions


def monthly_series(s: Series) -> pd.Series:
    """The series as monthly means indexed by month start, for lag analyses."""
    months = monthly(s.points)
    index = pd.to_datetime([f"{label(m)}-01" for m in months])
    return pd.Series(list(months.values()), index=index).asfreq("MS")


def caution_facts(card: str, cautions: list[str]) -> list[Fact]:
    """A guardrail's warning, said on the card it concerns."""
    return [Fact(card, f"Caution. {line}") for line in cautions]


def lag_facts(
    card: str, response: Series, drivers: list[Series], deseasonalise: bool
) -> list[Fact]:
    y = monthly_series(response)
    found = explore(
        response.area,
        (response.title, response.key, y),
        [(d.title, d.key, monthly_series(d)) for d in drivers],
        deseasonalise,
    )
    cautions = guardrails.lags(
        response.area,
        (response.title, y),
        [(d.title, monthly_series(d), d.warnings) for d in drivers],
        deseasonalise,
    )
    return [Fact(card, line) for line in found.summary] + caution_facts(card, cautions)


def correlation_cautions(response: Series, driver: Series, deseasonalise: bool) -> list[str]:
    a, b = monthly_series(response), monthly_series(driver)
    months = int(pd.concat([a, b], axis=1).dropna().shape[0])
    return guardrails.correlation(
        response.area, (response.title, a), (driver.title, b), deseasonalise, months
    )


@dataclass
class View:
    """What is open in the researcher's workspace, and the facts computed from it."""

    context: list[str]  # areas, period and processing, in plain lines
    series: list[Series]
    charts: list[str]  # the variable keys charted
    analyses: list[dict]  # as the interface saves them
    resolution: str = "monthly"  # of the charts
    extra: list[Fact] = field(default_factory=list)  # facts computed elsewhere, e.g. forecasts

    def find(self, area: str, key: str, resolution: str | None = None) -> Series | None:
        wanted = resolution or self.resolution
        same = [s for s in self.series if s.area == area and s.key == key]
        return next((s for s in same if s.resolution == wanted), same[0] if same else None)

    def facts(self) -> list[Fact]:
        facts: list[Fact] = []
        areas = list(dict.fromkeys(s.area for s in self.series))
        for key in self.charts:
            charted = [s for area in areas if (s := self.find(area, key))]
            for s in charted:
                facts.extend(series_facts(s))
            if len(charted) >= 2 and key != "spei" and (fact := comparison_fact(*charted[:2])):
                facts.append(fact)
        for n, analysis in enumerate(self.analyses, start=1):
            if analysis.get("kind") == "decomposition":
                for area in areas:
                    if s := self.find(area, analysis["variable"], "native"):
                        facts.extend(decomposition_facts(f"Decomposition {n}: {s.title}", s))
                continue
            if analysis.get("kind") == "trend":
                from engine.trend import trend  # here, since trend builds on these helpers

                for area in areas:
                    if s := self.find(area, analysis["variable"]):
                        card = f"Trend {n}: {s.title}"
                        found = trend(s.area, s.title, s.key, s.units, s.points)
                        facts += [Fact(card, line) for line in found.summary]
                        facts += caution_facts(card, found.cautions)
                continue
            if analysis.get("kind") == "lags":
                for area in areas:
                    response = self.find(area, analysis["response"])
                    drivers = [d for k in analysis.get("drivers", []) if (d := self.find(area, k))]
                    if response:
                        card = f"Lags {n}: {response.title}"
                        facts.extend(
                            lag_facts(card, response, drivers, analysis.get("deseasonalise", True))
                        )
                continue
            if analysis.get("kind") != "correlation":
                continue
            for area in areas:
                response = self.find(area, analysis["response"])
                driver = self.find(area, analysis["driver"])
                if response and driver:
                    card = f"Correlation {n}: {response.title} and {driver.title}"
                    kept = analysis.get("deseasonalise", True)
                    facts.append(correlation_fact(card, response, driver, kept))
                    facts += caution_facts(card, correlation_cautions(response, driver, kept))
        return facts + self.extra

    def cards(self) -> list[str]:
        return list(dict.fromkeys(f.card for f in self.facts()))

    def sheet(self) -> str:
        """The facts as the model reads them, grouped by card."""
        lines = ["What is open in Magonia now (computed by code from the researcher's data):"]
        lines += [f"- {line}" for line in self.context]
        card = None
        for fact in self.facts():
            if fact.card != card:
                card = fact.card
                lines.append(f"\n[{card}]")
            lines.append(f"- {fact.text}")
        if card is None:
            lines.append("\nNo charts or analyses are open yet.")
        return "\n".join(lines)

    def read(self, area: str, variable: str, year: int | None = None) -> str:
        """Monthly values of one year, or annual means of every year, for a closer look."""
        wanted = variable.strip().lower()
        found = [
            s
            for s in self.series
            if s.area.lower() == area.strip().lower()
            and wanted in (s.key, s.title.lower(), s.title.lower().split("-")[0])
        ]
        # the series the charts show, when an analysis fetched the same one at another step
        s = next((s for s in found if s.resolution == self.resolution), found[0] if found else None)
        if s is None:
            have = "; ".join(f"{x.area} {x.title}" for x in self.series) or "nothing"
            return f"No series for {area} {variable}. Open now: {have}."
        months = monthly(s.points)
        if year is None:
            years = {}
            for m, v in months.items():
                years.setdefault(m // 12, []).append(v)
            parts = [f"{y} {fmt(fmean(vs), s.key)} ({len(vs)} months)" for y, vs in years.items()]
            return f"{s.area}, {s.title}, annual means: " + "; ".join(parts) + "."
        parts = [f"{MONTHS[m % 12]} {fmt(v, s.key)}" for m, v in months.items() if m // 12 == year]
        if not parts:
            return f"{s.area}, {s.title}: no observations in {year}."
        unit = f" ({s.units})" if s.units else ""
        return f"{s.area}, {s.title}{unit}, monthly means in {year}: " + ", ".join(parts) + "."
