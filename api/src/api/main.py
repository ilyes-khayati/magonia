import math
from datetime import date
from typing import Literal

import engine
from engine.areas import AreaError, make_area
from engine.catalogue import get_variable
from engine.earth_engine import EarthEngineError, connect
from engine.series import Masking, series, size_warnings
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Magonia API", version="0.0.1")


class SeriesRequest(BaseModel):
    geometry: dict  # GeoJSON geometry, e.g. a polygon drawn on the map
    start: date
    end: date
    variable: Literal["ndvi", "lst", "spei"] = "ndvi"
    masking: Masking = "pixel"  # how flagged observations are removed
    scale: int | None = Field(None, ge=1, le=48)  # SPEI time scale in months


class SeriesPoint(BaseModel):
    date: date
    value: float | None
    sd: float | None
    n_pixels: int
    masked: bool


class SeriesResponse(BaseModel):
    variable: str
    name: str
    units: str
    points: list[SeriesPoint]
    warnings: list[str]


def number(value: float) -> float | None:
    return None if math.isnan(value) else value


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": engine.__version__}


@app.post("/series")
def get_series(request: SeriesRequest) -> SeriesResponse:
    """A variable over the given area, one point per image."""
    if request.end <= request.start:
        raise HTTPException(422, "end must be after start")
    try:
        area = make_area(request.geometry, "Area")
    except AreaError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        connect()
    except EarthEngineError as exc:
        raise HTTPException(503, str(exc)) from exc

    variable = get_variable(request.variable)
    try:
        table = series(
            request.variable,
            request.geometry,
            request.start.isoformat(),
            request.end.isoformat(),
            request.masking,
            request.scale,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    points = [
        SeriesPoint(
            date=row.date.date(),
            value=number(row.value),
            sd=number(row.sd),
            n_pixels=row.n_pixels,
            masked=row.masked,
        )
        for row in table.itertuples()
    ]
    return SeriesResponse(
        variable=variable.key,
        name=f"{variable.name}-{request.scale}" if request.scale else variable.name,
        units=variable.units,
        points=points,
        warnings=size_warnings(variable, area.area_km2),
    )
