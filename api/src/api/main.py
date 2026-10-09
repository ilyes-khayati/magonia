import math
from datetime import date

import engine
from engine.earth_engine import EarthEngineError, connect
from engine.series import ndvi_series
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Magonia API", version="0.0.1")


class SeriesRequest(BaseModel):
    geometry: dict  # GeoJSON geometry, e.g. a polygon drawn on the map
    start: date
    end: date


class SeriesPoint(BaseModel):
    date: date
    ndvi: float | None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": engine.__version__}


@app.post("/series")
def series(request: SeriesRequest) -> list[SeriesPoint]:
    """Mean NDVI over the given area, one value per 16-day MODIS composite."""
    if request.end <= request.start:
        raise HTTPException(422, "end must be after start")
    try:
        connect()
    except EarthEngineError as exc:
        raise HTTPException(503, str(exc)) from exc
    table = ndvi_series(request.geometry, request.start.isoformat(), request.end.isoformat())
    return [
        SeriesPoint(date=day.date(), ndvi=None if math.isnan(value) else value)
        for day, value in zip(table["date"], table["ndvi"])
    ]
