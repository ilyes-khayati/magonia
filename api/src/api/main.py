import itertools
import json
import logging
import sqlite3
import time
from collections.abc import Iterator
from datetime import date, timedelta
from functools import cache
from typing import Annotated, Literal

import engine
import pandas as pd
from engine import assistant, facts, guardrails, layers, notebook
from engine.areas import AreaError, make_area
from engine.board import Pinned
from engine.catalogue import CATALOGUE, get_variable
from engine.coherence import CoherenceError, coherence
from engine.decompose import DecompositionError, decompose
from engine.earth_engine import EarthEngineError, check, connect, plainly
from engine.explain import Explanation, Pair, describe, explain, stability
from engine.fulltext import FullTextError
from engine.lags import explore
from engine.leakage import LeakageError, audit
from engine.library import Library, Uploads
from engine.library import default_path as library_path
from engine.models import ForecastError, design, forecast
from engine.phenology import PhenologyError, phenology
from engine.pipeline import Request, fingerprint
from engine.prepare import Resolution
from engine.purity import PurityError, purity
from engine.purity import sample as sample_pixels
from engine.series import Masking, band_name
from engine.trend import trend
from engine.verify import installed as verifier_installed
from engine.verify import judge_for
from fastapi import Depends, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.jobs import Runner, cache_key, execute
from api.store import Store, default_path

app = FastAPI(title="Magonia API", version="0.0.1")
# what went wrong in detail goes to the log; the researcher is told what it means for them
log = logging.getLogger("magonia")

# Larger areas make Earth Engine requests slow or fail; the limit is stated, not hidden (DATA-07)
MAX_AREA_KM2 = 10_000


def check_area(geometry: dict, name: str) -> float:
    """The area in km², or a 422 explaining why it cannot be used."""
    try:
        area_km2 = make_area(geometry, name).area_km2
    except AreaError as exc:
        raise HTTPException(422, str(exc)) from exc
    if area_km2 > MAX_AREA_KM2:
        raise HTTPException(
            422,
            f"{name} covers {area_km2:,.0f} km²; areas are limited to {MAX_AREA_KM2:,} km² "
            "for now. Draw a smaller area.",
        )
    return area_km2


@cache
def get_store() -> Store:
    return Store(default_path())


@cache
def get_runner() -> Runner:
    return Runner()


def magon_settings(store: Store) -> dict:
    """What the researcher chose for Magon in the settings; empty keeps the environment's."""
    return json.loads(store.setting("magon") or "{}")


def get_provider(store: Annotated[Store, Depends(get_store)]) -> assistant.Provider:
    return assistant.from_environment(magon_settings(store))


def get_library(provider: Annotated[assistant.Provider, Depends(get_provider)]) -> Library:
    """The papers Magonia has read, ranked by meaning with the provider's embedding model."""
    return Library(library_path(), embed=getattr(provider, "embed", None))


StoreDep = Annotated[Store, Depends(get_store)]
RunnerDep = Annotated[Runner, Depends(get_runner)]
ProviderDep = Annotated[assistant.Provider, Depends(get_provider)]
LibraryDep = Annotated[Library, Depends(get_library)]


# Models


class EarthEngineStatus(BaseModel):
    connected: bool
    project: str | None
    error: str | None = None


class EarthEngineProject(BaseModel):
    project: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9-]*$")


class SeriesRequest(BaseModel):
    """What to extract. Give either a saved area_id or a GeoJSON geometry."""

    area_id: int | None = None
    geometry: dict | None = None  # e.g. a polygon drawn on the map
    workspace_id: int | None = None  # keep the result with this workspace
    start: date
    end: date
    variable: Literal[tuple(CATALOGUE)] = "ndvi"  # type: ignore[valid-type]
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


class Job(BaseModel):
    id: int
    status: Literal["queued", "running", "done", "failed"]
    error: str | None = None
    request: dict
    result: SeriesResponse | None = None


class AreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    geometry: dict


class Area(BaseModel):
    id: int
    workspace_id: int
    name: str
    geometry: dict
    area_km2: float


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    settings: dict | None = None  # whatever the interface needs to restore its state


class Conversation(BaseModel):
    id: int
    workspace_id: int
    title: str | None  # null until named: the interface shows its first question
    first_question: str | None
    messages: int
    created: str
    updated: str


class ConversationIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)


class ChatMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    details: dict = {}  # for answers: searches, papers found and the citation check
    created: str


class View(BaseModel):
    """What is open in the interface when a question is asked."""

    page: str = "map"
    charts: list[str] = []  # the variables charted
    resolution: Resolution = "monthly"  # of the charts
    analyses: list[dict] = []  # as the interface saves them
    series: list[SeriesRequest] = []  # every series shown or used, each with its area_id
    display: str | None = None  # how the Data page shows the series, if changed
    board: list[dict] = []  # what the researcher pinned: title, text, trust and date
    focus: str | None = Field(None, max_length=200)  # the card asked about, by its title


class Question(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    view: View | None = None


class WorkspaceSummary(BaseModel):
    id: int
    name: str
    created: str
    updated: str
    deleted: str | None = None  # when it was moved to Recently deleted


class Workspace(WorkspaceSummary):
    settings: dict
    areas: list[Area]
    jobs: list[Job]


# General


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": engine.__version__}


@app.get("/catalogue")
def catalogue() -> list[dict]:
    """Every variable Magonia can extract, with its source, resolution and licence."""
    return [variable.to_dict() for variable in CATALOGUE.values()]


# Earth Engine connection


@app.get("/earth-engine")
def earth_engine_status(store: StoreDep) -> EarthEngineStatus:
    """Whether Earth Engine answers with the saved project (or EE_PROJECT from .env)."""
    project = store.setting("ee_project")
    try:
        return EarthEngineStatus(connected=True, project=check(project))
    except EarthEngineError as exc:
        return EarthEngineStatus(connected=False, project=project, error=str(exc))


@app.put("/earth-engine")
def set_earth_engine_project(body: EarthEngineProject, store: StoreDep) -> EarthEngineStatus:
    """Save the Earth Engine project, once it has answered."""
    try:
        project = check(body.project)
    except EarthEngineError as exc:
        raise HTTPException(422, str(exc)) from exc
    store.set_setting("ee_project", project)
    return EarthEngineStatus(connected=True, project=project)


# Jobs


def job_view(store: Store, job: dict) -> Job:
    result = store.result(job["result_key"]) if job["status"] == "done" else None
    return Job(
        id=job["id"],
        status=job["status"],
        error=job["error"],
        request=job["request"],
        result=result,
    )


@app.post("/jobs", status_code=202)
def submit_job(body: SeriesRequest, store: StoreDep, runner: RunnerDep) -> Job:
    """Start extracting a series. Poll GET /jobs/{id} until it is done or failed."""
    if body.end <= body.start:
        raise HTTPException(422, "end must be after start")
    if body.workspace_id is not None and not store.workspace(body.workspace_id):
        raise HTTPException(404, "workspace not found")
    if body.area_id is not None:
        area = store.area(body.area_id)
        if not area:
            raise HTTPException(404, "area not found")
        geometry = area["geometry"]
    elif body.geometry is not None:
        geometry = body.geometry
    else:
        raise HTTPException(422, "give an area_id or a geometry")

    request = Request(
        variable=body.variable,
        geometry=geometry,
        start=body.start.isoformat(),
        end=body.end.isoformat(),
        masking=body.masking,
        scale=body.scale,
        resolution=body.resolution,
        max_gap=body.max_gap,
    )
    check_area(geometry, "This area")
    try:  # check everything that can be checked before calling Earth Engine
        band_name(get_variable(body.variable), body.masking, body.scale)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    key = cache_key(request)
    cached = store.result(key) is not None
    job_id = store.create_job(
        request.to_dict(), key, body.workspace_id, body.area_id, "done" if cached else "queued"
    )
    if not cached:
        runner.submit(execute, store, job_id, request, key)
    return job_view(store, store.job(job_id))


@app.get("/jobs/{job_id}")
def get_job(job_id: int, store: StoreDep) -> Job:
    """A job's status, and its result once it is done."""
    job = store.job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job_view(store, job)


# Layers: a variable drawn on the map for one month, the pixel under a point, and the
# variable's own pixels over an area. Earth Engine draws the tiles; its URLs last some hours.

TILES: dict[str, tuple[float, dict]] = {}
TILE_LIFE = 3600  # seconds


def earth_engine(store: Store) -> None:
    try:
        connect(store.setting("ee_project"))  # None falls back to EE_PROJECT in .env
    except EarthEngineError as exc:
        raise HTTPException(503, str(exc)) from exc


def layer_variable(key: str, scale: int | None) -> None:
    try:
        band_name(get_variable(key), "pixel", scale)
        layers.legend(key)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc).strip("\"'")) from exc


@app.get("/layers/{key}/legend")
def layer_legend(key: str) -> dict:
    """The colour ramp a variable is drawn with, and the values at its ends."""
    layer_variable(key, 3 if key == "spei" else None)
    return layers.legend(key).to_dict()


@app.get("/layers/{key}/tiles")
def layer_tiles(
    key: str,
    store: StoreDep,
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
    scale: int | None = None,
) -> dict:
    """A tile URL template for one month of a variable, with its legend."""
    layer_variable(key, scale)
    name = f"{key}|{month}|{scale}"
    if (held := TILES.get(name)) and time.time() - held[0] < TILE_LIFE:
        return held[1]
    earth_engine(store)
    try:
        found = layers.tiles(key, month, scale)
    except Exception as exc:
        log.exception("tiles for %s %s", key, month)
        raise HTTPException(
            502, plainly(exc, f"draw {get_variable(key).name} for {month}")
        ) from exc
    TILES[name] = (time.time(), found)
    return found


@app.get("/areas/{area_id}/purity")
def area_purity(
    area_id: int,
    store: StoreDep,
    start: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")] = "2003-01",
    end: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")] = "2022-12",
) -> dict:
    """How much of each MODIS pixel over and around an area is annual crop, from its average
    year split between the most seasonal and the most even vegetated pixels nearby."""
    area = store.area(area_id)
    if not area:
        raise HTTPException(404, "area not found")
    key = fingerprint(
        {"purity": area["geometry"], "start": start, "end": end, "engine": engine.__version__}
    )
    if (held := store.result(key)) is not None:
        return held
    earth_engine(store)
    last = pd.Period(end, "M").end_time.date() + timedelta(days=1)
    try:
        pixels = sample_pixels(area["geometry"], f"{start}-01", last.isoformat())
    except Exception as exc:
        log.exception("purity of area %s", area_id)
        raise HTTPException(502, plainly(exc, "read the pixels around this area")) from exc
    try:
        found = purity(pixels, area["geometry"], area["name"]).to_dict()
    except PurityError as exc:
        raise HTTPException(422, str(exc)) from exc
    store.save_result(key, found)
    return found


class PointRequest(BaseModel):
    variable: str
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    start: date
    end: date
    scale: int | None = None


@app.post("/inspect")
def inspect_point(body: PointRequest, store: StoreDep) -> dict:
    """The value of the pixel under a point, image by image: one pixel, not an area mean."""
    layer_variable(body.variable, body.scale)
    if body.end <= body.start:
        raise HTTPException(422, "end must be after start")
    request = body.model_dump(mode="json") | {
        "lon": round(body.lon, 5),
        "lat": round(body.lat, 5),
    }
    key = fingerprint({"point": request})
    if (held := store.result(key)) is not None:
        return held
    earth_engine(store)
    variable = get_variable(body.variable)
    try:
        points = layers.point_series(
            body.variable, body.lon, body.lat, request["start"], request["end"], body.scale
        )
    except Exception as exc:
        log.exception("inspect %s", request)
        raise HTTPException(502, plainly(exc, "read this pixel")) from exc
    found = {
        **request,
        "name": variable.name,
        "units": variable.units,
        "pixel_m": variable.pixel_m,
        "points": [
            {"date": p["date"], "value": None if p["value"] is None else round(p["value"], 4)}
            for p in points
        ],
    }
    store.save_result(key, found)
    return found


@app.get("/areas/{area_id}/pixels")
def area_pixels(area_id: int, variable: str, store: StoreDep) -> dict:
    """The outlines of a variable's own pixels that touch an area: what its mean is made of."""
    area = store.area(area_id)
    if not area:
        raise HTTPException(404, "area not found")
    layer_variable(variable, 3 if variable == "spei" else None)
    key = fingerprint({"pixels": variable, "geometry": area["geometry"]})
    if (held := store.result(key)) is not None:
        return held
    earth_engine(store)
    try:
        grid = layers.pixel_grid(variable, area["geometry"])
    except Exception as exc:
        log.exception("pixels of area %s", area_id)
        raise HTTPException(502, plainly(exc, "outline the pixels")) from exc
    found = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": f["geometry"]}
            for f in grid["features"]
        ],
        "pixel_m": get_variable(variable).pixel_m,
    }
    store.save_result(key, found)
    return found


# Workspaces


def existing_workspace(store: Store, workspace_id: int, deleted: bool = False) -> dict:
    workspace = store.workspace(workspace_id, deleted=deleted)
    if not workspace:
        raise HTTPException(404, "workspace not found")
    return workspace


@app.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, store: StoreDep) -> WorkspaceSummary:
    workspace = store.create_workspace(body.name)
    return WorkspaceSummary(**{key: workspace[key] for key in WorkspaceSummary.model_fields})


@app.get("/workspaces")
def list_workspaces(store: StoreDep, deleted: bool = False) -> list[WorkspaceSummary]:
    """The workspaces in use, or with deleted=true those deleted in the last 30 days."""
    return store.workspaces(deleted=deleted)


@app.get("/workspaces/{workspace_id}")
def open_workspace(workspace_id: int, store: StoreDep) -> Workspace:
    """Everything in a workspace, including finished results, without recomputing. A series
    asked for again is a new job; only the latest for each request is sent, or a workspace in
    long use would send every run it ever made."""
    workspace = existing_workspace(store, workspace_id)
    latest = {json.dumps(job["request"], sort_keys=True): job for job in store.jobs(workspace_id)}
    return Workspace(
        **workspace,
        areas=store.areas(workspace_id),
        jobs=[job_view(store, job) for job in latest.values()],
    )


@app.patch("/workspaces/{workspace_id}")
def update_workspace(workspace_id: int, body: WorkspaceUpdate, store: StoreDep) -> Workspace:
    existing_workspace(store, workspace_id)
    store.update_workspace(workspace_id, body.name, body.settings)
    return open_workspace(workspace_id, store)


@app.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: int, store: StoreDep, forever: bool = False) -> Response:
    """Move a workspace to Recently deleted, or with forever=true remove it from there."""
    if forever:
        if not existing_workspace(store, workspace_id, deleted=True)["deleted"]:
            raise HTTPException(404, "workspace not in Recently deleted")
        store.delete_workspace_forever(workspace_id)
    else:
        existing_workspace(store, workspace_id)
        store.delete_workspace(workspace_id)
    return Response(status_code=204)


@app.post("/workspaces/{workspace_id}/restore")
def restore_workspace(workspace_id: int, store: StoreDep) -> WorkspaceSummary:
    existing_workspace(store, workspace_id, deleted=True)
    store.restore_workspace(workspace_id)
    return store.workspace(workspace_id)


# Areas


def existing_area(store: Store, area_id: int, deleted: bool = False) -> dict:
    area = store.area(area_id, deleted=deleted)
    if not area:
        raise HTTPException(404, "area not found")
    return area


@app.post("/workspaces/{workspace_id}/areas", status_code=201)
def create_area(workspace_id: int, body: AreaIn, store: StoreDep) -> Area:
    """Save a named area. Invalid polygons are refused with the reason."""
    existing_workspace(store, workspace_id)
    area_km2 = check_area(body.geometry, body.name)
    try:
        return store.create_area(workspace_id, body.name, body.geometry, area_km2)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"an area called {body.name!r} already exists") from None


@app.get("/workspaces/{workspace_id}/areas")
def list_areas(workspace_id: int, store: StoreDep) -> list[Area]:
    existing_workspace(store, workspace_id)
    return store.areas(workspace_id)


@app.patch("/areas/{area_id}")
def rename_area(area_id: int, body: Rename, store: StoreDep) -> Area:
    existing_area(store, area_id)
    try:
        store.rename_area(area_id, body.name)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"an area called {body.name!r} already exists") from None
    return store.area(area_id)


@app.delete("/areas/{area_id}", status_code=204)
def delete_area(area_id: int, store: StoreDep) -> Response:
    """Delete an area; it can be restored for 30 days, unless a new area takes its name."""
    existing_area(store, area_id)
    store.delete_area(area_id)
    return Response(status_code=204)


@app.post("/areas/{area_id}/restore")
def restore_area(area_id: int, store: StoreDep) -> Area:
    existing_area(store, area_id, deleted=True)
    store.restore_area(area_id)
    return store.area(area_id)


# Analyses


def series_request(body: SeriesRequest, store: Store) -> tuple[dict, Request]:
    """The saved area and the extraction request a series body describes."""
    area = store.area(body.area_id) if body.area_id is not None else None
    if area is None:
        raise HTTPException(404, "area not found")
    request = Request(
        variable=body.variable,
        geometry=area["geometry"],
        start=body.start.isoformat(),
        end=body.end.isoformat(),
        masking=body.masking,
        scale=body.scale,
        resolution=body.resolution,
        max_gap=body.max_gap,
    )
    return area, request


@app.post("/decomposition")
def decomposition(body: SeriesRequest, store: StoreDep) -> dict:
    """Wavelet trend and seasonal parts of a series already extracted at its native step,
    with the sentences the assistant is given about them."""
    if body.resolution != "native":
        raise HTTPException(422, "decompose the series at its native time step")
    area, request = series_request(body, store)
    result = store.result(cache_key(request))
    if result is None:
        raise HTTPException(409, "this series has not been extracted yet")
    points = result["points"]
    dates = [p["date"] for p in points]
    values = [p["value"] if (not p["masked"] or p["filled"]) else None for p in points]
    try:
        parts = decompose(pd.Series(dates), pd.Series(values, dtype=float), body.variable)
    except DecompositionError as exc:
        raise HTTPException(422, str(exc)) from exc
    series = facts.Series(area["name"], body.variable, result["name"], result["units"], points)
    summary, cautions = split_cautions(facts.decomposition_facts("", series))
    return {**parts.to_dict(), "area_id": area["id"], "summary": summary, "cautions": cautions}


def split_cautions(found: list[facts.Fact]) -> tuple[list[str], list[str]]:
    """A card's sentences, and apart from them the guardrails' cautions (AI-03)."""
    summary = [f.text for f in found if not f.text.startswith("Caution. ")]
    cautions = [f.text.removeprefix("Caution. ") for f in found if f.text.startswith("Caution. ")]
    return summary, cautions


@app.post("/phenology")
def season_dates(body: SeriesRequest, store: StoreDep) -> dict:
    """Start, peak and end of the growing season, year by year, from NDVI at its native
    step (ANA-05)."""
    if body.resolution != "native":
        raise HTTPException(422, "season dates need the series at its native time step")
    s = cached_series(body, store)
    try:
        found = phenology(s.area, s.title, s.key, s.points)
    except PhenologyError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"area_id": body.area_id, **found.to_dict()}


class NotebookRequest(BaseModel):
    title: str = Field("Magonia analysis", max_length=120)
    kind: Literal[
        "experiment",
        "decomposition",
        "trend",
        "phenology",
        "lags",
        "correlation",
        "scales",
        "coherence",
        "leakage",
    ]
    options: dict = {}  # the analysis' own choices, as the interface saves them
    series: list[SeriesRequest] = Field(min_length=1)  # in the order the analysis uses them


@app.post("/notebook")
def export_notebook(body: NotebookRequest, store: StoreDep) -> Response:
    """The analysis as a Jupyter notebook that reproduces it from the data it used (REP-01)."""
    used = []
    for request in body.series:
        s = cached_series(request, store)
        used.append(
            {
                "area": s.area,
                "key": s.key,
                "title": s.title,
                "units": s.units,
                "points": s.points,
                "product": get_variable(s.key).product,
                "resolution": request.resolution,
            }
        )
    nb = notebook.notebook(body.title, body.kind, body.options, used)
    name = "".join(c if c.isalnum() else "-" for c in body.title.lower()).strip("-") or "magonia"
    return Response(
        notebook.dumps(nb),
        media_type="application/x-ipynb+json",
        headers={"Content-Disposition": f'attachment; filename="{name}.ipynb"'},
    )


@app.post("/trend")
def series_trend(body: SeriesRequest, store: StoreDep) -> dict:
    """Theil–Sen slope and Mann–Kendall test of a series' annual means (ANA-04)."""
    s = cached_series(body, store)
    found = trend(s.area, s.title, s.key, s.units, s.points)
    return {"area_id": body.area_id, **found.to_dict()}


class LagsRequest(BaseModel):
    response: SeriesRequest
    drivers: list[SeriesRequest] = []
    deseasonalise: bool = True


def cached_series(body: SeriesRequest, store: Store) -> facts.Series:
    """A series already extracted, as the facts read it, or 409 if it is not there yet."""
    area, request = series_request(body, store)
    result = store.result(cache_key(request))
    if result is None:
        raise HTTPException(409, "this series has not been extracted yet")
    return facts.Series(
        area["name"],
        body.variable,
        result["name"],
        result["units"],
        result["points"],
        warnings=result.get("warnings", []),
    )


class CoherenceRequest(BaseModel):
    response: SeriesRequest
    driver: SeriesRequest
    deseasonalise: bool = False


@app.post("/coherence")
def wavelet_coherence(body: CoherenceRequest, store: StoreDep) -> dict:
    """Where in time and at which periods two series move together, and which leads."""
    if body.response.resolution == "seasonal" or body.driver.resolution == "seasonal":
        raise HTTPException(422, "coherence needs monthly values; use native or monthly")
    response = cached_series(body.response, store)
    driver = cached_series(body.driver, store)
    key = fingerprint(
        {
            "coherence": [
                cache_key(series_request(s, store)[1]) for s in (body.response, body.driver)
            ],
            "deseasonalise": body.deseasonalise,
            "engine": engine.__version__,
        }
    )
    if (held := store.result(key)) is not None:
        return held
    a, b = facts.monthly_series(response), facts.monthly_series(driver)
    if body.deseasonalise:
        a = a - a.groupby(a.index.month).transform("mean")
        b = b - b.groupby(b.index.month).transform("mean")
    try:
        found = coherence(a, b, response.title, driver.title, response.area).to_dict()
    except CoherenceError as exc:
        raise HTTPException(422, str(exc)) from exc
    store.save_result(key, found)
    return found


class LeakageRequest(BaseModel):
    response: SeriesRequest
    test_years: int = Field(3, ge=1, le=10)


@app.post("/leakage")
def leakage_audit(body: LeakageRequest, store: StoreDep) -> dict:
    """How much of a wavelet-hybrid forecast's skill comes from decomposing the whole record."""
    if body.response.resolution == "seasonal":
        raise HTTPException(422, "the audit needs monthly values; use native or monthly")
    response = cached_series(body.response, store)
    key = fingerprint(
        {
            "leakage": cache_key(series_request(body.response, store)[1]),
            "test_years": body.test_years,
            "engine": engine.__version__,
        }
    )
    if (held := store.result(key)) is not None:
        return held
    try:
        found = audit(
            facts.monthly_series(response), response.title, response.area, body.test_years
        ).to_dict()
    except LeakageError as exc:
        raise HTTPException(422, str(exc)) from exc
    store.save_result(key, found)
    return found


@app.post("/lags")
def lags(body: LagsRequest, store: StoreDep) -> dict:
    """How a series remembers itself and which past months of its drivers stand out,
    with the sentences the assistant is given about them."""
    if body.response.resolution == "seasonal":
        raise HTTPException(422, "lags are in months; use native or monthly values")
    response = cached_series(body.response, store)
    drivers = [cached_series(d, store) for d in body.drivers]
    found = explore(
        response.area,
        (response.title, response.key, facts.monthly_series(response)),
        [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
        body.deseasonalise,
    )
    cautions = guardrails.lags(
        response.area,
        (response.title, facts.monthly_series(response)),
        [(d.title, facts.monthly_series(d), d.warnings) for d in drivers],
        body.deseasonalise,
    )
    return {"area_id": body.response.area_id, **found.to_dict(), "cautions": cautions}


class ModelsRequest(BaseModel):
    response: SeriesRequest
    drivers: list[SeriesRequest] = []
    own_lags: list[int] | None = Field(None, max_length=12)  # None: recommended by code
    driver_lags: dict[str, list[int]] | None = None  # by variable; a driver left out: recommended
    test_years: int = Field(3, ge=1, le=10)
    models: list[Literal["Ridge", "RandomForest", "XGBoost", "MLP", "LSTM", "GRU", "TCN"]] = Field(
        ["Ridge", "RandomForest", "XGBoost"], min_length=1
    )
    params: dict[str, dict[str, float]] | None = None  # by model; a model left out is tuned
    calendar: bool = True
    rolling: bool = True  # also test on earlier windows


# forecasts being fitted, and the last error of each, by key; results go to the store
FITTING: set[str] = set()
FAILED: dict[str, str] = {}


def models_key(body: ModelsRequest, store: Store) -> str:
    """Identical choices on identical series share one forecast."""
    series = [cache_key(series_request(s, store)[1]) for s in [body.response, *body.drivers]]
    choices = body.model_dump(include={"own_lags", "driver_lags", "test_years"})
    # later choices count only when changed, so earlier forecasts keep their key
    later = body.model_dump(
        include={"models", "params", "calendar", "rolling"}, exclude_defaults=True
    )
    if later.get("models") == ["Ridge", "RandomForest", "XGBoost"]:
        later.pop("models")
    # settings matter only for the models chosen
    params = {m: p for m, p in (body.params or {}).items() if m in body.models}
    later.pop("params", None)
    if params:
        later["params"] = params
    return fingerprint({"forecast": series, **choices, **later, "engine": engine.__version__})


def forecast_cautions(result: dict, response: facts.Series, drivers: list[facts.Series]) -> list:
    """The guardrails on a forecast, worked out when read, so earlier results gain them too."""
    warnings = [w for d in drivers for w in guardrails.footprint(d.title, d.warnings)]
    return guardrails.models(response.area, result, warnings)


def under_current_name(lines: list[str], stored: dict, area: str) -> list[str]:
    """Stored sentences begin with the area's name when they were written; an area renamed
    since is given its name now. Results stored before the name was kept give it in their
    first sentence."""
    old = stored.get("area") or (lines[0].partition(": ")[0] if lines else area)
    return [area + line[len(old) :] if line.startswith(f"{old}: ") else line for line in lines]


def fit_forecast(store: Store, key: str, response: facts.Series, drivers: list[facts.Series], body):
    try:
        found = forecast(
            response.area,
            (response.title, response.key, facts.monthly_series(response)),
            [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
            body.own_lags,
            body.driver_lags,
            body.test_years,
            models=body.models,
            params=body.params,
            calendar=body.calendar,
            rolling=body.rolling,
        )
        store.save_result(key, {**found.to_dict(), "area": response.area})
    except ForecastError as exc:
        FAILED[key] = str(exc)
    except Exception:  # any failure must reach the user, not vanish
        log.exception("fitting %s", key)
        FAILED[key] = (
            "The models could not be fitted. Try fewer predictors or lags, or a longer period."
        )
    finally:
        FITTING.discard(key)


@app.post("/models")
def models(body: ModelsRequest, store: StoreDep, runner: RunnerDep, reply: Response) -> dict:
    """The chosen models (Ridge, Random Forest, XGBoost) forecasting a series one month ahead,
    tested on its last years against two baselines. Fitting runs in the background: ask again with the same
    body until the status is done."""
    if body.response.resolution == "seasonal":
        raise HTTPException(422, "forecasts are monthly; use native or monthly values")
    response = cached_series(body.response, store)
    drivers = [cached_series(d, store) for d in body.drivers]
    key = models_key(body, store)
    if (result := store.result(key)) is not None:
        return {
            "status": "done",
            **result,
            "summary": under_current_name(result["summary"], result, response.area),
            "cautions": forecast_cautions(result, response, drivers),
        }
    if key in FAILED:
        return {"status": "failed", "error": FAILED.pop(key)}
    if key not in FITTING:
        FITTING.add(key)
        runner.submit(fit_forecast, store, key, response, drivers, body)
    reply.status_code = 202
    return {"status": "running"}


def explain_forecast(store, key, models_result, response, drivers, body) -> None:
    try:
        X, y, _, test_start = design(
            (response.title, response.key, facts.monthly_series(response)),
            [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
            body.own_lags,
            body.driver_lags,
            body.test_years,
            body.calendar,
        )
        train = X.index < test_start
        params = {m["name"]: m["params"] for m in models_result["models"]}
        found = explain(X[train], y[train], params)
        store.save_result(key, found.to_dict())
    except Exception:  # any failure must reach the user, not vanish
        log.exception("explaining %s", key)
        FAILED[key] = "The models could not be explained. Fit them again, then try once more."
    finally:
        FITTING.discard(key)


def explanation_summary(stored: dict, area: str) -> list[str]:
    """The sentences are written when read, so that results explained earlier gain what the
    engine has learned to say since, and the area's name now."""
    found = Explanation(
        stored["importance"],
        stored["families"],
        [Pair(**p) for p in stored["agreement"]],
        stored["seeds"],
        stored.get("family_range", {}),
        stored.get("dropped", {}),
    )
    return describe(area, found)


def explanations_key(body: ModelsRequest, store: Store) -> str:
    return fingerprint(
        {
            "explain": models_key(body, store),
            "with": "ranges, drop-column, own explanations, months and effects",
        }
    )


@app.post("/explanations")
def explanations(body: ModelsRequest, store: StoreDep, runner: RunnerDep, reply: Response) -> dict:
    """Permutation importance, family shares and agreement of fitted models, on their
    training years. Runs in the background like the models: ask again until done."""
    fitted = store.result(models_key(body, store))
    if fitted is None:
        raise HTTPException(409, "fit the models first")
    key = explanations_key(body, store)
    if (result := store.result(key)) is not None:
        area = cached_series(body.response, store).area
        return {"status": "done", **result, "summary": explanation_summary(result, area)}
    if key in FAILED:
        return {"status": "failed", "error": FAILED.pop(key)}
    if key not in FITTING:
        FITTING.add(key)
        response = cached_series(body.response, store)
        drivers = [cached_series(d, store) for d in body.drivers]
        runner.submit(explain_forecast, store, key, fitted, response, drivers, body)
    reply.status_code = 202
    return {"status": "running"}


def check_stability(store, key, models_result, response, drivers, body) -> None:
    try:
        X, y, _, test_start = design(
            (response.title, response.key, facts.monthly_series(response)),
            [(d.title, d.key, facts.monthly_series(d)) for d in drivers],
            body.own_lags,
            body.driver_lags,
            body.test_years,
            body.calendar,
        )
        params = {m["name"]: m["params"] for m in models_result["models"]}
        held = stability(response.area, X, y, params, test_start)
        store.save_result(key, {**held.to_dict(), "area": response.area})
    except Exception:  # any failure must reach the user, not vanish
        log.exception("stability %s", key)
        FAILED[key] = (
            "Stability could not be checked: the record may be too short for earlier windows."
        )
    finally:
        FITTING.discard(key)


def stability_key(body: ModelsRequest, store: Store) -> str:
    return fingerprint({"stability": models_key(body, store), "retune": True})


@app.post("/stability")
def explanation_stability(
    body: ModelsRequest, store: StoreDep, runner: RunnerDep, reply: Response
) -> dict:
    """What each fitted model leans on when its training years end earlier: whether its
    explanation holds across training windows. Runs in the background: ask again until done."""
    fitted = store.result(models_key(body, store))
    if fitted is None:
        raise HTTPException(409, "fit the models first")
    key = stability_key(body, store)
    if (result := store.result(key)) is not None:
        area = cached_series(body.response, store).area
        return {
            "status": "done",
            **result,
            "summary": under_current_name(result["summary"], result, area),
        }
    if key in FAILED:
        return {"status": "failed", "error": FAILED.pop(key)}
    if key not in FITTING:
        FITTING.add(key)
        response = cached_series(body.response, store)
        drivers = [cached_series(d, store) for d in body.drivers]
        runner.submit(check_stability, store, key, fitted, response, drivers, body)
    reply.status_code = 202
    return {"status": "running"}


# The assistant


@app.get("/assistant")
def assistant_info(provider: ProviderDep) -> dict:
    return {"name": assistant.NAME, "model": provider.name}


class MagonSettings(BaseModel):
    """How Magon answers. A field left empty keeps the default (the environment's server and
    model, the model's own temperature)."""

    model_url: str | None = Field(None, max_length=200, pattern=r"^(https?://\S+|scripted)$")
    model: str | None = Field(None, max_length=100)
    temperature: float | None = Field(None, ge=0, le=1.5)
    detail: Literal["concise", "detailed"] = "concise"
    papers_per_search: int = Field(6, ge=3, le=10)
    # keyword: OpenAlex on the words; hybrid: on the words and on meaning, merged
    search: Literal["keyword", "hybrid"] = "keyword"
    # who checks that a cited passage supports a sentence: the chat model, or a verifier
    # withdraw: a statement its papers do not support leaves the answer; mark: it stays, flagged
    claims: Literal["withdraw", "mark"] = "withdraw"
    # MiniCheck RoBERTa by default: on SciFact it agrees with expert labels as well as the chat
    # model does, four times faster, and it is not the model that wrote the answer
    verifier: Literal["model", "nli", "minicheck-roberta", "minicheck-deberta"] = (
        "minicheck-roberta"
    )


@app.get("/assistant/settings")
def get_magon_settings(store: StoreDep, provider: ProviderDep) -> dict:
    """The settings saved, with the server, model and checker in use, so the form can show
    them. The checker in use is the chat model when the chosen verifier is not installed."""
    saved = MagonSettings(**magon_settings(store))
    return {
        **saved.model_dump(),
        "in_use": {
            "model_url": getattr(provider, "url", None),
            "model": getattr(provider, "model", None),
            "verifier": saved.verifier if verifier_installed(saved.verifier) else "model",
        },
    }


@app.put("/assistant/settings")
def set_magon_settings(body: MagonSettings, store: StoreDep) -> MagonSettings:
    store.set_setting("magon", body.model_dump_json())
    return body


@app.get("/assistant/models")
def assistant_models(provider: ProviderDep, url: str | None = None) -> dict:
    """The chat models installed on the model server (the one in use, or the one given)."""
    server = url or getattr(provider, "url", None)
    if not server:
        return {"models": [], "error": None}
    try:
        return {"models": assistant.installed_models(server), "error": None}
    except (OSError, ValueError):
        return {"models": [], "error": "The model server did not answer at this address."}


def existing_conversation(store: Store, conversation_id: int, deleted: bool = False) -> dict:
    conversation = store.conversation(conversation_id, deleted=deleted)
    if not conversation or not store.workspace(conversation["workspace_id"]):
        raise HTTPException(404, "conversation not found")
    return conversation


@app.get("/workspaces/{workspace_id}/conversations")
def list_conversations(workspace_id: int, store: StoreDep) -> list[Conversation]:
    """The conversations with the assistant in this workspace, the latest first."""
    existing_workspace(store, workspace_id)
    return store.conversations(workspace_id)


@app.post("/workspaces/{workspace_id}/conversations", status_code=201)
def create_conversation(
    workspace_id: int, store: StoreDep, body: ConversationIn | None = None
) -> Conversation:
    existing_workspace(store, workspace_id)
    return store.create_conversation(workspace_id, body.title if body else None)


@app.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int, body: ConversationIn, store: StoreDep
) -> Conversation:
    existing_conversation(store, conversation_id)
    if body.title is not None:
        store.rename_conversation(conversation_id, body.title)
    return store.conversation(conversation_id)


@app.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, store: StoreDep) -> Response:
    """Delete a conversation; it can be restored for 30 days."""
    existing_conversation(store, conversation_id)
    store.delete_conversation(conversation_id)
    return Response(status_code=204)


@app.post("/conversations/{conversation_id}/restore")
def restore_conversation(conversation_id: int, store: StoreDep) -> Conversation:
    existing_conversation(store, conversation_id, deleted=True)
    store.restore_conversation(conversation_id)
    return store.conversation(conversation_id)


@app.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, store: StoreDep) -> list[ChatMessage]:
    """A conversation with the assistant, oldest message first."""
    existing_conversation(store, conversation_id)
    return store.messages(conversation_id)


MASKING = {
    "pixel": "cloudy pixels removed",
    "date": "cloudy dates removed",
    "none": "no cloud filter",
}


def workspace_view(store: Store, workspace_id: int, view: View) -> facts.View:
    """The series the interface shows, read from the result cache, with their context."""
    areas = {a["id"]: a for a in store.areas(workspace_id)}
    series, loading, used = [], [], {}
    for s in view.series:
        area = areas.get(s.area_id)
        if area is None:
            continue
        used[area["name"]] = area["area_km2"]
        request = Request(
            variable=s.variable,
            geometry=area["geometry"],
            start=s.start.isoformat(),
            end=s.end.isoformat(),
            masking=s.masking,
            scale=s.scale,
            resolution=s.resolution,
            max_gap=s.max_gap,
        )
        result = store.result(cache_key(request))
        if result is None:
            loading.append(f"{area['name']} {s.variable.upper()}")
            continue
        series.append(
            facts.Series(
                area["name"],
                s.variable,
                result["name"],
                result["units"],
                result["points"],
                s.resolution,
                result.get("warnings", []),
            )
        )
    name = store.workspace(workspace_id)["name"]
    context = [f'The researcher is in the workspace "{name}", on the {view.page} page.']
    if view.focus:
        context.append(
            f'The question is about the card "{view.focus}": answer about what it shows.'
        )
    if used:
        context.append(
            "Areas: " + ", ".join(f"{n} ({km2:.2f} km²)" for n, km2 in used.items()) + "."
        )
    if view.series:
        first = view.series[0]
        last_month = (first.end - timedelta(days=1)).isoformat()[:7]
        context.append(
            f"Period {first.start.isoformat()[:7]} to {last_month}, {first.resolution} values, "
            f"{MASKING[first.masking]}, gaps of up to {first.max_gap} filled."
        )
    if view.display:
        context.append(
            f"The Data page charts show {view.display}; the facts below describe the series as "
            "extracted."
        )
    if loading:
        context.append("Still loading, so not described: " + ", ".join(loading) + ".")
    # the board is given to Magon as evidence it can cite (pinned_items), not as facts here
    extra = forecast_facts(store, view, areas)
    return facts.View(
        context, series, view.charts, view.analyses, view.resolution, extra, focus=view.focus
    )


def pinned_items(board: list[dict]) -> list[Pinned]:
    """The board as Magon's memory; an item sent without a trust level is the researcher's."""
    return [
        Pinned(
            str(b.get("title", ""))[:80],
            str(b.get("text", "")),
            str(b.get("trust", "note")),
            str(b.get("pinned", "")),
        )
        for b in board
    ]


def series_warnings(store: Store, request: SeriesRequest | None) -> list[str]:
    if request is None:
        return []
    result = store.result(cache_key(series_request(request, store)[1]))
    return result.get("warnings", []) if result else []


def forecast_facts(store: Store, view: View, areas: dict[int, dict]) -> list[facts.Fact]:
    """What finished forecasts found, read from the cache; fitting is not started here."""
    found = []
    for n, analysis in enumerate(view.analyses, start=1):
        if analysis.get("kind") != "models":
            continue
        # an experiment from the Model page ran on one area; older cards on every area
        chosen = analysis.get("area")
        for area_id, area in areas.items():
            if chosen is not None and area_id != chosen:
                continue
            mine = {
                s.variable: s
                for s in view.series
                if s.area_id == area_id and s.resolution == view.resolution
            }
            if analysis.get("response") not in mine:
                continue
            later = {
                k: analysis[k]
                for k in ("models", "params", "calendar", "rolling")
                if analysis.get(k) is not None
            }
            body = ModelsRequest(
                response=mine[analysis["response"]],
                drivers=[mine[k] for k in analysis.get("drivers", []) if k in mine],
                own_lags=analysis.get("own_lags"),
                driver_lags=analysis.get("driver_lags"),
                test_years=analysis.get("test_years", 3),
                **later,
            )
            name = analysis.get("name") or f"Models {n}"
            card = f"{name}: {analysis['response'].upper()} forecast"
            key = models_key(body, store)
            if (result := store.result(key)) is not None:
                lines = under_current_name(result["summary"], result, area["name"])
                found += [facts.Fact(card, line) for line in lines]
                footprints = [
                    w
                    for k in analysis.get("drivers", [])
                    for w in guardrails.footprint(k.upper(), series_warnings(store, mine.get(k)))
                ]
                cautions = guardrails.models(area["name"], result, footprints)
                found += facts.caution_facts(card, cautions)
            elif key in FITTING:
                found.append(
                    facts.Fact(card, f"{area['name']}: the models are still being fitted.")
                )
            if (why := store.result(explanations_key(body, store))) is not None:
                card = f"{name}: what the models lean on"
                lines = explanation_summary(why, area["name"])
                found += [facts.Fact(card, line) for line in lines]
            if (held := store.result(stability_key(body, store))) is not None:
                card = f"{name}: stability across training windows"
                lines = under_current_name(held["summary"], held, area["name"])
                found += [facts.Fact(card, line) for line in lines]
    return found


# The researcher's library: their own PDFs, which Magonia reads and cites like papers. Each
# workspace has its own files; a file is then reached by its id, which is unique.

MAX_UPLOAD = 30_000_000


class Instructions(BaseModel):
    text: str = Field(max_length=assistant.MAX_INSTRUCTIONS)


@app.get("/workspaces/{workspace_id}/library")
def list_files(workspace_id: int, store: StoreDep, library: LibraryDep) -> list[dict]:
    existing_workspace(store, workspace_id)
    return Uploads(library.scoped(workspace_id)).all()


@app.post("/workspaces/{workspace_id}/library", status_code=201)
async def add_file(
    workspace_id: int, file: UploadFile, store: StoreDep, library: LibraryDep
) -> dict:
    """Read an uploaded PDF into the workspace's library: its passages, pages and embeddings."""
    existing_workspace(store, workspace_id)
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "The PDF is larger than 30 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, f"{file.filename} is not a PDF.")
    try:
        return Uploads(library.scoped(workspace_id)).add(file.filename or "file.pdf", data)
    except FullTextError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/library/{file_id}", status_code=204)
def remove_file(file_id: str, library: LibraryDep) -> None:
    """Remove a file from the library; it can be restored for 30 days."""
    try:
        Uploads(library).remove(file_id)
    except KeyError as exc:
        raise HTTPException(404, "No such file.") from exc


@app.post("/library/{file_id}/restore")
def restore_file(file_id: str, library: LibraryDep) -> dict:
    try:
        return Uploads(library).restore(file_id)
    except KeyError as exc:
        raise HTTPException(404, "No such file.") from exc


@app.get("/library/{file_id}/pdf")
def read_file(file_id: str, library: LibraryDep) -> FileResponse:
    """The file itself, shown in the browser (#page=6 opens it at page 6)."""
    try:
        path = Uploads(library).pdf(file_id)
        title = Uploads(library).get(file_id)["filename"]
    except KeyError as exc:
        raise HTTPException(404, "No such file.") from exc
    if path is None:
        raise HTTPException(404, "This file was added before Magonia kept PDFs; add it again.")
    return FileResponse(
        path, media_type="application/pdf", filename=title, content_disposition_type="inline"
    )


@app.get("/workspaces/{workspace_id}/instructions")
def get_instructions(workspace_id: int, store: StoreDep) -> Instructions:
    """How the researcher wants Magonia to answer in this workspace."""
    existing_workspace(store, workspace_id)
    return Instructions(text=store.setting(f"instructions:{workspace_id}") or "")


@app.put("/workspaces/{workspace_id}/instructions")
def set_instructions(workspace_id: int, body: Instructions, store: StoreDep) -> Instructions:
    existing_workspace(store, workspace_id)
    store.set_setting(f"instructions:{workspace_id}", body.text)
    return body


@app.post("/conversations/{conversation_id}/chat")
def chat(
    conversation_id: int,
    body: Question,
    store: StoreDep,
    provider: ProviderDep,
    library: LibraryDep,
) -> StreamingResponse:
    """Ask the assistant. Events stream back as JSON lines and the answer is saved at the end.

    With a view of what is open, the assistant is given facts computed from the researcher's
    cached results. Events: view (the cards it was given), read (a closer look at a series),
    proposal (an analysis it proposes, which the researcher may add),
    text (a piece of the answer), search, search_failed, papers, reading and passages (the
    open-access papers read in full, and the passages chosen from them), verifying, check (the
    final answer after its citations and pages were checked, with how well each cited
    statement is supported by its papers) and error.
    """
    workspace_id = existing_conversation(store, conversation_id)["workspace_id"]
    # earlier answers carry the papers they cited, so that a follow-up can cite them again
    history = [
        {
            "role": m["role"],
            "content": m["content"],
            "papers": m["details"].get("papers", []),
            "cited": m["details"].get("check", {}).get("cited", []),
        }
        for m in store.messages(conversation_id)
    ]
    view = workspace_view(store, workspace_id, body.view) if body.view else None
    question = {"role": "user", "content": body.content}
    instructions = store.setting(f"instructions:{workspace_id}") or ""
    chosen = MagonSettings(**magon_settings(store))
    events = assistant.answer(
        provider,
        [*history, question],
        view=view,
        library=library.scoped(workspace_id),  # this workspace's files only
        instructions=instructions,
        papers_per_search=chosen.papers_per_search,
        search_mode=chosen.search,
        detail=chosen.detail,
        judge=judge_for(chosen.verifier),
        withdraw_unsupported=chosen.claims == "withdraw",
        board=pinned_items(body.view.board) if body.view else [],
    )
    # fail with a clear status before streaming starts, if the model cannot be reached: the
    # route and view events come before the model is asked anything
    head = []
    try:
        for event in events:
            head.append(event)
            if event["type"] not in ("route", "view"):
                break
    except assistant.ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    store.add_message(conversation_id, "user", body.content)

    def stream() -> Iterator[str]:
        said, searches, papers, verdict, cards, reads, proposals = [], [], [], None, [], [], []
        board_given: list[dict] = []
        passages, read = [], {}
        route = None
        claim_test = None  # a claim tested on the researcher's data, with its verdict
        try:
            for event in itertools.chain(head, events):
                match event["type"]:
                    case "text":
                        said.append(event["text"])
                    case "rewrite":
                        said = [event["text"]]
                    case "search":
                        searches.append(event["query"])
                    case "papers":
                        papers.extend(event["papers"])
                    case "check":
                        verdict = event
                    case "view":
                        cards = event["cards"]
                    case "read":
                        reads.append({k: event[k] for k in ("area", "variable", "year")})
                    case "proposal":
                        proposals.append(event["proposal"])
                    case "route":
                        route = {k: event[k] for k in ("kind", "source")}
                    case "board":
                        board_given = event["items"]
                    case "passages":
                        passages.extend(event["passages"])
                        read.update(event["read"])
                    case "claim_test":
                        claim_test = event["test"]
                yield json.dumps(event) + "\n"
        except assistant.ProviderError as exc:
            log.warning("chat stopped: %s", exc)
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"
        finally:  # keep what was said, even if the reader left early
            details = {"searches": searches, "papers": papers, "cards": cards, "reads": reads}
            if proposals:
                details["proposals"] = proposals
            if board_given:
                details["board"] = board_given  # the pinned items it was given, [B1]…
            if route:
                details["route"] = route
            if claim_test:
                details["claim_test"] = claim_test
            if passages or read:
                details["passages"] = passages
                details["read"] = read
            if verdict:
                details["check"] = {
                    k: verdict[k] for k in ("cited", "removed", "unverified", "pages_removed")
                }
                if "numbers" in verdict:
                    details["numbers"] = verdict["numbers"]
                if verdict.get("app"):
                    details["app"] = verdict["app"]
                if "timings" in verdict:
                    details["timings"] = verdict["timings"]  # where the answer's time went
                if "support" in verdict:
                    details["support"] = verdict["support"]
                    details["faithfulness"] = verdict["faithfulness"]
                if verdict.get("board_cited"):
                    details["board_cited"] = verdict["board_cited"]
                if verdict.get("withdrawn"):
                    details["withdrawn"] = verdict["withdrawn"]
                if verdict.get("uncited"):
                    # the sentences that cite nothing: shown while streaming, and kept, or
                    # they vanished from the answer when the conversation was reopened
                    details["uncited"] = verdict["uncited"]
            text = verdict["text"] if verdict else "".join(said)
            store.add_message(conversation_id, "assistant", text, details)

    return StreamingResponse(stream(), media_type="application/x-ndjson")
