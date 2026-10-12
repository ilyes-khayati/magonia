import math
from datetime import date

import engine
from engine.earth_engine import EarthEngineError, connect
from engine.series import Masking, ndvi_series
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Magonia API", version="0.0.1")


class SeriesRequest(BaseModel):
    geometry: dict  # GeoJSON geometry, e.g. a polygon drawn on the map
    start: date
    end: date
    masking: Masking = "pixel"  # how cloudy observations are removed


class SeriesPoint(BaseModel):
    date: date
    ndvi: float | None
    sd: float | None
    n_pixels: int
    masked: bool


def number(value: float) -> float | None:
    return None if math.isnan(value) else value


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": engine.__version__}


@app.post("/series")
def series(request: SeriesRequest) -> list[SeriesPoint]:
    """NDVI over the given area, one point per 16-day MODIS composite."""
    if request.end <= request.start:
        raise HTTPException(422, "end must be after start")
    try:
        connect()
    except EarthEngineError as exc:
        raise HTTPException(503, str(exc)) from exc
    table = ndvi_series(
        request.geometry, request.start.isoformat(), request.end.isoformat(), request.masking
    )
    return [
        SeriesPoint(
            date=row.date.date(),
            ndvi=number(row.ndvi),
            sd=number(row.sd),
            n_pixels=row.n_pixels,
            masked=row.masked,
        )
        for row in table.itertuples()
    ]
