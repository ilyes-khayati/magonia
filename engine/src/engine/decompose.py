"""Wavelet decomposition of a series into a slow trend and a seasonal part.

The method of Bounouh et al. (2024) and of the 2026 paper: multiresolution analysis with the
discrete Meyer wavelet, at the series' own cadence, with the boundary between trend and
season set nearest one year. The series is mirrored at both ends to soften edge effects, the
trend is the lowest-frequency component, and the seasonal part is what remains, so the two
add back exactly to the series. Results are then averaged by month.

The filter is two-sided: the trend at a date uses later observations too. It describes the
past; it is not a forecast.
"""

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pywt

WAVELET = "dmey"
TARGET_DAYS = 365.25  # the trend keeps cycles longer than about a year
CADENCE_DAYS = {"ndvi": 16.0, "savi": 16.0, "lst": 8.0, "spei": 365.25 / 12}
PAD = 0.5  # share of the series mirrored at each end


def semi_period(level: int, cadence_days: float) -> float:
    """Days of the boundary between the trend and the rest, at a given level."""
    return 2**level * cadence_days / (2 * pywt.central_frequency(WAVELET))


def level_for(cadence_days: float) -> int:
    """The level whose boundary falls nearest one year: 5 at 16 days, 6 at 8, 4 monthly."""
    return min(range(2, 9), key=lambda j: abs(semi_period(j, cadence_days) - TARGET_DAYS))


def split(values: np.ndarray, level: int) -> tuple[np.ndarray, np.ndarray]:
    """Trend and seasonal part of an evenly spaced series without gaps."""
    n = len(values)
    p = int(PAD * n)
    padded = np.concatenate([values[:p][::-1], values, values[-p:][::-1]])
    # PyWavelets warns that dmey's long filter reaches the edges at these levels; the
    # mirrored padding is there for that, and the paper's results are made the same way
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Level value of .* is too high")
        components = pywt.mra(padded, WAVELET, level=level, transform="dwt", mode="symmetric")
    trend = components[0][p : p + n]
    return trend, values - trend


@dataclass
class Decomposition:
    monthly: pd.DataFrame  # date, value, trend, seasonal: monthly means of the native components
    level: int
    cadence_days: float
    semi_period_days: float
    interpolated: int  # empty dates filled by straight lines before decomposing

    def to_dict(self) -> dict:
        def number(x: float) -> float | None:
            return None if pd.isna(x) else float(x)

        return {
            "wavelet": WAVELET,
            "level": self.level,
            "cadence_days": self.cadence_days,
            "semi_period_days": round(self.semi_period_days, 1),
            "interpolated": self.interpolated,
            "points": [
                {
                    "date": row.date.date().isoformat(),
                    "value": number(row.value),
                    "trend": number(row.trend),
                    "seasonal": number(row.seasonal),
                }
                for row in self.monthly.itertuples()
            ],
        }


class DecompositionError(ValueError):
    """The series cannot be decomposed, e.g. it is too short."""


def decompose(dates: pd.Series, values: pd.Series, key: str) -> Decomposition:
    """Decompose a series at its native cadence and average the parts by month.

    Empty dates inside the series are filled by straight lines first, as in the paper;
    empty dates at either end are dropped.
    """
    series = pd.Series(values.to_numpy(float), index=pd.to_datetime(dates)).sort_index()
    series = series.loc[series.first_valid_index() : series.last_valid_index()]
    cadence = CADENCE_DAYS[key]
    level = level_for(cadence)
    # the trend needs at least a few cycles of its own length to mean anything
    if len(series) * cadence < 3 * TARGET_DAYS:
        raise DecompositionError("At least three years of data are needed for a decomposition.")
    gaps = int(series.isna().sum())
    filled = series.interpolate()
    trend, seasonal = split(filled.to_numpy(), level)
    native = pd.DataFrame(
        {"value": filled.to_numpy(), "trend": trend, "seasonal": seasonal}, index=series.index
    )
    monthly = native.resample("MS").mean().rename_axis("date").reset_index()
    return Decomposition(monthly, level, cadence, semi_period(level, cadence), gaps)
