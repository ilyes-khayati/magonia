"""Time series of satellite variables over an area."""

import ee
import pandas as pd

NDVI_COLLECTION = "MODIS/061/MOD13Q1"
NDVI_SCALE = 0.0001  # MOD13Q1 stores NDVI as integers


def ndvi_series(geometry: dict, start: str, end: str) -> pd.DataFrame:
    """Mean MODIS NDVI over a GeoJSON geometry, one row per 16-day composite."""
    area = ee.Geometry(geometry)
    images = ee.ImageCollection(NDVI_COLLECTION).filterDate(start, end).select("NDVI")

    def mean_over_area(image):
        value = image.reduceRegion(ee.Reducer.mean(), area, scale=250).get("NDVI")
        return ee.Feature(None, {"date": image.date().format("YYYY-MM-dd"), "ndvi": value})

    features = ee.FeatureCollection(images.map(mean_over_area)).getInfo()["features"]
    return to_table(features)


def to_table(features: list[dict]) -> pd.DataFrame:
    """Turn Earth Engine features into a table of dates and NDVI values."""
    table = pd.DataFrame([f["properties"] for f in features], columns=["date", "ndvi"])
    table["date"] = pd.to_datetime(table["date"])
    table["ndvi"] = pd.to_numeric(table["ndvi"]) * NDVI_SCALE
    return table
