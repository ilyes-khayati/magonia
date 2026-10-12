import math
from datetime import date
from typing import Literal

import engine
from engine.earth_engine import EarthEngineError, connect
from engine.pipeline import Request, run
from engine.prepare import Resolution
from engine.series import Masking, fetch
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
    resolution: Resolution = "native"
    max_gap: int = Field(2, ge=0, le=12)  # longest run of empty dates to fill; 0 turns filling off


class SeriesPoint(BaseModel):
    date: date
    value: float | None
    sd: float | None
    n_pixels: int
    masked: bool
    filled: bool
    n_obs: int
    n_valid: int


class SeriesResponse(BaseModel):
    variable: str
    name: str
    units: str
    points: list[SeriesPoint]
    warnings: list[str]
    provenance: dict


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
        connect()
    except EarthEngineError as exc:
        raise HTTPException(503, str(exc)) from exc

    try:
        result = run(
            Request(
                variable=request.variable,
                geometry=request.geometry,
                start=request.start.isoformat(),
                end=request.end.isoformat(),
                masking=request.masking,
                scale=request.scale,
                resolution=request.resolution,
                max_gap=request.max_gap,
            ),
            fetch=fetch,
        )
    except ValueError as exc:  # includes invalid areas
        raise HTTPException(422, str(exc)) from exc

    variable = result.provenance["variable"]
    points = [
        SeriesPoint(
            date=row.date.date(),
            value=number(row.value),
            sd=number(row.sd),
            n_pixels=row.n_pixels,
            masked=row.masked,
            filled=row.filled,
            n_obs=row.n_obs,
            n_valid=row.n_valid,
        )
        for row in result.table.itertuples()
    ]
    return SeriesResponse(
        variable=variable["key"],
        name=f"{variable['name']}-{request.scale}" if request.scale else variable["name"],
        units=variable["units"],
        points=points,
        warnings=result.warnings,
        provenance=result.provenance,
    )
