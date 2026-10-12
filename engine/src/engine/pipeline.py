"""One request from area to prepared series, with a record of every step."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

import ee
import pandas as pd

import engine
from engine.areas import make_area
from engine.catalogue import Variable, get_variable
from engine.prepare import Resolution, aggregate, fill_gaps
from engine.series import Masking, band_name, fetch, size_warnings, to_table


@dataclass(frozen=True)
class Request:
    variable: str
    geometry: dict
    start: str  # ISO dates; end is exclusive
    end: str
    masking: Masking = "pixel"
    scale: int | None = None  # SPEI time scale in months
    resolution: Resolution = "native"
    max_gap: int = 2  # longest run of empty rows to fill; 0 turns filling off

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Result:
    table: pd.DataFrame
    provenance: dict
    warnings: list[str] = field(default_factory=list)


def run(request: Request, fetch: Callable[..., list[dict]] = fetch) -> Result:
    """Extract, mask, aggregate and fill a series as the request describes.

    fetch is the Earth Engine call; tests pass recorded responses instead.
    """
    variable = get_variable(request.variable)
    band = band_name(variable, request.masking, request.scale)
    area = make_area(request.geometry, "Area")

    features = fetch(
        request.variable,
        request.geometry,
        request.start,
        request.end,
        request.masking,
        request.scale,
    )
    raw = to_table(features, variable, request.masking)
    table = aggregate(raw, request.resolution)
    if request.max_gap:
        table = fill_gaps(table, request.max_gap)

    record = provenance(request, variable, band, area.area_km2, raw, table)
    return Result(table, record, size_warnings(variable, area.area_km2))


def fingerprint(data: dict) -> str:
    """A short, stable hash of JSON data: the same content always gives the same text."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def provenance(
    request: Request,
    variable: Variable,
    band: str,
    area_km2: float,
    raw: pd.DataFrame,
    table: pd.DataFrame,
) -> dict:
    """Where a series comes from and what was done to it, as plain JSON data."""
    if variable.sampling == "centre":
        sampling = "value of the grid cell containing the centre of the area"
        quality = {"step": "quality", "method": "none", "rule": variable.quality}
    else:
        sampling = "area-weighted mean of the pixels overlapping the area"
        quality = {
            "step": "quality",
            "method": request.masking,
            "rule": variable.quality,
            "dates_without_data": int(raw["masked"].sum()),
        }
    filling = (
        {
            "step": "fill gaps",
            "method": "linear interpolation in time",
            "max_gap": request.max_gap,
            "filled": int(table["filled"].sum()),
        }
        if request.max_gap
        else {"step": "fill gaps", "method": "off"}
    )
    record = {
        "variable": {
            "key": variable.key,
            "name": variable.name,
            "units": variable.units,
            "product": variable.product,
            "collection": variable.collection,
            "band": band,
            "resolution": variable.resolution,
            "cadence": variable.cadence,
            "licence": variable.licence,
            "citation": variable.citation,
        },
        "area": {
            "area_km2": round(area_km2, 4),
            "geometry_fingerprint": fingerprint(request.geometry),
            "sampling": sampling,
        },
        "window": {"start": request.start, "end": request.end},
        "steps": [
            {"step": "extract", "source": "Google Earth Engine", "dates": len(raw)},
            quality,
            {
                "step": "aggregate",
                "resolution": request.resolution,
                "periods": len(table),
                "empty_periods": int(table["n_valid"].eq(0).sum()),
            },
            filling,
        ],
        "software": {"engine": engine.__version__, "earthengine-api": ee.__version__},
    }
    record["id"] = fingerprint(record)
    return record
