"""Time series of satellite variables over an area."""

from typing import Literal

import ee
import pandas as pd

NDVI_COLLECTION = "MODIS/061/MOD13Q1"
NDVI_SCALE = 0.0001  # MOD13Q1 stores NDVI as integers
CLOUDY = 2  # SummaryQA: 0 good, 1 marginal, 2 snow or ice, 3 cloudy

Masking = Literal["pixel", "date", "none"]
COLUMNS = ["date", "ndvi", "sd", "n_pixels", "masked"]


def ndvi_series(geometry: dict, start: str, end: str, masking: Masking = "pixel") -> pd.DataFrame:
    """MODIS NDVI over a GeoJSON geometry, one row per 16-day composite.

    masking chooses how cloudy observations (SummaryQA >= 2) are removed:
    "pixel" drops cloudy pixels and averages the rest, "date" drops the whole
    date when the area's mean SummaryQA is 2 or more, "none" keeps everything.
    """
    if masking not in ("pixel", "date", "none"):
        raise ValueError(f"masking must be 'pixel', 'date' or 'none', not {masking!r}")

    area = ee.Geometry(geometry)
    images = ee.ImageCollection(NDVI_COLLECTION).filterDate(start, end)
    stats = (
        ee.Reducer.mean()
        .combine(ee.Reducer.stdDev(), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )

    def summarise(image):
        quality = image.select("SummaryQA")
        ndvi = image.select("NDVI")
        if masking == "pixel":
            ndvi = ndvi.updateMask(quality.lt(CLOUDY))
        values = ndvi.reduceRegion(stats, area, scale=250)
        mean_quality = quality.reduceRegion(ee.Reducer.mean(), area, scale=250).get("SummaryQA")
        return ee.Feature(
            None,
            {
                "date": image.date().format("YYYY-MM-dd"),
                "ndvi": values.get("NDVI_mean"),
                "sd": values.get("NDVI_stdDev"),
                "n_pixels": values.get("NDVI_count"),
                "quality": mean_quality,
            },
        )

    features = ee.FeatureCollection(images.map(summarise)).getInfo()["features"]
    return to_table(features, masking)


def to_table(features: list[dict], masking: Masking = "pixel") -> pd.DataFrame:
    """Turn Earth Engine features into one row per date.

    A date is masked when it has no usable value: every pixel was cloudy, the
    whole date was dropped, or Earth Engine returned nothing.
    """
    table = pd.DataFrame(
        [f["properties"] for f in features], columns=["date", "ndvi", "sd", "n_pixels", "quality"]
    )
    table["date"] = pd.to_datetime(table["date"])
    table["ndvi"] = pd.to_numeric(table["ndvi"]) * NDVI_SCALE
    table["sd"] = pd.to_numeric(table["sd"]) * NDVI_SCALE
    table["n_pixels"] = pd.to_numeric(table["n_pixels"]).fillna(0).astype(int)

    if masking == "date":
        cloudy = pd.to_numeric(table["quality"]) >= CLOUDY
        table.loc[cloudy, ["ndvi", "sd"]] = float("nan")
        table.loc[cloudy, "n_pixels"] = 0

    table["masked"] = table["ndvi"].isna()
    return table[COLUMNS]
