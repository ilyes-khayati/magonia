import math
from pathlib import Path

import pandas as pd
import pytest

from engine.prepare import aggregate, fill_gaps

DATA = Path(__file__).parent / "data"
NAN = float("nan")


def make_series(dates, values):
    values = [NAN if v is None else v for v in values]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "value": values,
            "sd": [0.1] * len(values),
            "n_pixels": [18] * len(values),
            "masked": [math.isnan(v) for v in values],
        }
    )


def daily(values):
    return make_series(pd.date_range("2023-01-01", periods=len(values)), values)


def test_short_gap_is_filled_linearly():
    table = fill_gaps(daily([1.0, None, None, 4.0]))
    assert list(table["value"]) == pytest.approx([1.0, 2.0, 3.0, 4.0])
    assert list(table["filled"]) == [False, True, True, False]
    assert table["masked"][1]  # a filled value is still not an observation


def test_interpolation_follows_time_not_rows():
    table = fill_gaps(make_series(["2023-01-01", "2023-01-02", "2023-01-11"], [0.0, None, 10.0]))
    assert table["value"][1] == pytest.approx(1.0)


def test_long_gap_stays_empty():
    table = fill_gaps(daily([1.0, None, None, None, 5.0]), max_gap=2)
    assert table["value"].isna().sum() == 3
    assert not table["filled"].any()


def test_gaps_at_the_edges_stay_empty():
    table = fill_gaps(daily([None, 2.0, 3.0, None]))
    assert table["value"].isna().tolist() == [True, False, False, True]


def test_native_resolution_counts_each_date():
    table = aggregate(daily([1.0, None]))
    assert list(table["n_obs"]) == [1, 1]
    assert list(table["n_valid"]) == [1, 0]


def test_monthly_mean_uses_only_real_observations():
    table = aggregate(
        make_series(["2023-01-01", "2023-01-17", "2023-02-02"], [1.0, None, 3.0]), "monthly"
    )
    assert list(table["date"]) == list(pd.to_datetime(["2023-01-01", "2023-02-01"]))
    assert list(table["value"]) == [1.0, 3.0]
    assert list(table["n_obs"]) == [2, 1]
    assert list(table["n_valid"]) == [1, 1]


def test_month_without_observations_is_masked_not_invented():
    table = aggregate(
        make_series(["2023-01-01", "2023-02-01", "2023-03-01"], [1.0, None, 3.0]), "monthly"
    )
    assert table["masked"].tolist() == [False, True, False]
    assert math.isnan(table["value"][1])
    assert fill_gaps(table)["value"][1] == pytest.approx(2.0, abs=0.1)


def test_winter_starts_in_december():
    table = aggregate(
        make_series(["2023-12-15", "2024-01-15", "2024-03-15"], [1.0, 3.0, 5.0]), "seasonal"
    )
    assert list(table["date"]) == list(pd.to_datetime(["2023-12-01", "2024-03-01"]))
    assert list(table["value"]) == [2.0, 5.0]


def test_unknown_resolution_is_rejected():
    with pytest.raises(ValueError, match="resolution"):
        aggregate(daily([1.0]), "weekly")


@pytest.mark.parametrize(
    ("file", "column"), [("reference_ndvi_16day.csv", "NDVI"), ("reference_lst_8day.csv", "LST")]
)
def test_monthly_means_match_the_reference(file, column):
    raw = pd.read_csv(DATA / file, parse_dates=["date"])
    table = raw.rename(columns={column: "value", f"{column}_sd": "sd", f"{column}_n": "n_pixels"})
    table["masked"] = table["value"].isna()
    monthly = aggregate(table, "monthly").set_index("date")

    reference = pd.read_csv(DATA / "reference_monthly.csv", parse_dates=["date"], index_col="date")
    assert len(monthly) == len(reference) == 298
    assert monthly["value"].to_numpy() == pytest.approx(reference[column].to_numpy(), abs=1e-9)
