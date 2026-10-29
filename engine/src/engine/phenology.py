"""When the growing season starts, peaks and ends, year by year (requirement ANA-05).

The series is put on a regular 8-day step, smoothed lightly (Savitzky–Golay), and each season
is found around its peak rather than within a calendar year, since in the Mediterranean the
season runs from autumn to spring and crosses the new year. Around each peak the lowest values
before and after are the season's bases; the start is when the value first climbs a fifth of
the way from the base before to the peak, the end when it last stays above a fifth of the way
down to the base after (a threshold method, as in TIMESAT). Amplitude is the peak above the
mean of the two bases.
"""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

THRESHOLD = 0.2  # share of the climb from base to peak that marks start and end
WEAK = 0.1  # an NDVI amplitude below this leaves the dates uncertain
STEP = "8D"


@dataclass
class Season:
    year: int  # the year of the peak
    start: str
    peak: str
    end: str
    length: int  # days
    peak_value: float
    amplitude: float


@dataclass
class Phenology:
    seasons: list[Season]
    smoothed: list[dict]  # date and value, for the chart
    summary: list[str]
    cautions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class PhenologyError(ValueError):
    """Too little data, or a variable without a growing season."""


def smooth(dates: pd.Series, values: pd.Series) -> pd.Series:
    s = pd.Series(values.to_numpy(dtype=float), index=pd.to_datetime(dates)).dropna()
    s = s[~s.index.duplicated()].sort_index()
    if len(s) < 46:
        raise PhenologyError("Phenology needs at least two years of observations.")
    regular = s.resample(STEP).mean().interpolate(limit_direction="both")
    return pd.Series(savgol_filter(regular.to_numpy(), 5, 2), index=regular.index)


def day(d: pd.Timestamp) -> str:
    return f"{d:%Y-%m-%d}"


def phenology(area: str, title: str, key: str, points: list[dict]) -> Phenology:
    if key != "ndvi":
        raise PhenologyError("Season dates are computed from NDVI, the greenness of vegetation.")
    frame = pd.DataFrame(points)
    values = frame["value"].where(~frame["masked"] | frame["filled"])
    s = smooth(frame["date"], values)
    # the usual day of the peak, from the average year
    usual = s.groupby(s.index.dayofyear // 8).mean()
    peak_doy = int(usual.idxmax() * 8 + 4)
    seasons = []
    for year in range(s.index[0].year, s.index[-1].year + 1):
        centre = pd.Timestamp(year, 1, 1) + pd.Timedelta(days=peak_doy - 1)
        if (
            centre - pd.Timedelta(days=182) < s.index[0]
            or centre + pd.Timedelta(days=182) > s.index[-1]
        ):
            continue  # the whole season is not in the record
        near = s[centre - pd.Timedelta(days=90) : centre + pd.Timedelta(days=90)]
        peak = near.idxmax()
        before = s[centre - pd.Timedelta(days=182) : peak]
        after = s[peak : centre + pd.Timedelta(days=182)]
        low1, low2 = before.idxmin(), after.idxmin()
        top = s[peak]
        rise = s[low1:peak]
        fall = s[peak:low2]
        start = rise[rise >= s[low1] + THRESHOLD * (top - s[low1])].index[0]
        end = fall[fall >= s[low2] + THRESHOLD * (top - s[low2])].index[-1]
        amplitude = float(top - (s[low1] + s[low2]) / 2)
        seasons.append(
            Season(
                peak.year,
                day(start),
                day(peak),
                day(end),
                int((end - start).days),
                float(top),
                amplitude,
            )
        )
    if len(seasons) < 2:
        raise PhenologyError(
            "Fewer than two whole seasons are in the record; choose a longer period."
        )

    who = f"{area}, {title}"

    def when(dates: list[str]) -> str:
        """The average day of the year of some dates, across the new year if they straddle it."""
        angles = [2 * np.pi * pd.Timestamp(d).dayofyear / 365.25 for d in dates]
        mean = np.arctan2(np.mean(np.sin(angles)), np.mean(np.cos(angles)))
        doy = round(float(mean % (2 * np.pi)) * 365.25 / (2 * np.pi)) or 365
        return f"{pd.Timestamp(2001, 1, 1) + pd.Timedelta(days=doy - 1):%d %b}"

    lengths = [x.length for x in seasons]
    amps = [x.amplitude for x in seasons]
    earliest = min(seasons, key=lambda x: pd.Timestamp(x.start) - pd.Timestamp(x.year, 1, 1))
    latest = max(seasons, key=lambda x: pd.Timestamp(x.start) - pd.Timestamp(x.year, 1, 1))
    dates = (
        f"{who}: over {len(seasons)} seasons the season starts around "
        f"{when([x.start for x in seasons])}, peaks around {when([x.peak for x in seasons])} and "
        f"ends around {when([x.end for x in seasons])}, lasting {np.mean(lengths):.0f} days on "
        f"average (from {min(lengths)} to {max(lengths)})."
    )
    extremes = (
        f"{who}: the peak stands {np.mean(amps):.2f} above the season's bases on average; the "
        f"earliest start was in the season peaking in {earliest.year} ({earliest.start}), the "
        f"latest in {latest.year} ({latest.start})."
    )
    summary = [dates, extremes]
    cautions = []
    if np.mean(amps) < WEAK:
        cautions.append(
            f"{who}: the yearly cycle is weak (amplitude {np.mean(amps):.2f}), so the season dates "
            "are uncertain; a sparse or evergreen cover may have no clear season."
        )
    smoothed = [{"date": day(d), "value": round(float(v), 4)} for d, v in s.items()]
    return Phenology(seasons, smoothed, summary, cautions)
