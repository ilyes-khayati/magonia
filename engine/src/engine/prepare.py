"""Preparation applied to a series after extraction: aggregation, then gap filling."""

from typing import Literal

import pandas as pd

Resolution = Literal["native", "monthly", "seasonal"]
PERIODS = {"monthly": "M", "seasonal": "Q-NOV"}  # Q-NOV: Dec-Feb, Mar-May, Jun-Aug, Sep-Nov
COLUMNS = ["date", "value", "sd", "n_pixels", "masked", "n_obs", "n_valid", "filled"]


def aggregate(table: pd.DataFrame, resolution: Resolution = "native") -> pd.DataFrame:
    """Average a series to months or seasons, one row per period.

    Only real observations are averaged; a period without any is masked.
    n_obs counts the dates in the period and n_valid the real observations.
    Seasons are labelled by their first month, so winter 2024 starts on 1 Dec 2023.
    """
    if resolution not in ("native", *PERIODS):
        raise ValueError(f"resolution must be native, monthly or seasonal, not {resolution!r}")
    table = table.copy()

    if resolution == "native":
        table["n_obs"] = 1
        table["n_valid"] = (~table["masked"]).astype(int)
    else:
        groups = table.groupby(table["date"].dt.to_period(PERIODS[resolution]))
        table = pd.DataFrame(
            {
                "value": groups["value"].mean(),  # pandas skips masked (empty) values
                "sd": groups["sd"].mean(),
                "n_pixels": groups["n_pixels"].mean().round().astype(int),
                "n_obs": groups.size(),
                "n_valid": groups["value"].count(),
            }
        )
        table["date"] = table.index.to_timestamp(how="start")
        table["masked"] = table["n_valid"] == 0

    table["filled"] = False
    return table[COLUMNS].reset_index(drop=True)


def fill_gaps(table: pd.DataFrame, max_gap: int = 2) -> pd.DataFrame:
    """Fill runs of at most max_gap empty rows by linear interpolation in time.

    Longer runs, and gaps at the start or end of the series, stay empty.
    Filled rows keep masked=True and get filled=True.
    """
    table = table.copy()
    missing = table["value"].isna()
    run = (missing != missing.shift()).cumsum()  # number each run of empty or present rows
    run_length = missing.groupby(run).transform("size")
    inside = table["value"].ffill().notna() & table["value"].bfill().notna()
    fillable = missing & (run_length <= max_gap) & inside

    interpolated = table.set_index("date")["value"].interpolate(method="time").to_numpy()
    table.loc[fillable, "value"] = interpolated[fillable.to_numpy()]
    table["filled"] = fillable
    return table
