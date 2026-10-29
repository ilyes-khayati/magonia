import itertools
import json
import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from functools import cache
from typing import Annotated, Literal

import engine
import pandas as pd
from engine import assistant, facts, guardrails, notebook
from engine.areas import AreaError, make_area
from engine.catalogue import CATALOGUE, get_variable
from engine.decompose import DecompositionError, decompose
from engine.earth_engine import EarthEngineError, check
from engine.explain import Explanation, Pair, describe, explain, stability
from engine.lags import explore
from engine.models import ForecastError, design, forecast
from engine.phenology import PhenologyError, phenology
from engine.pipeline import Request, fingerprint
from engine.prepare import Resolution
from engine.series import Masking, band_name
from engine.trend import trend
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.jobs import Runner, cache_key, execute
from api.store import Store, default_path

app = FastAPI(title="Magonia API", version="0.0.1")

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


@cache
def get_provider() -> assistant.Provider:
    return assistant.from_environment()


StoreDep = Annotated[Store, Depends(get_store)]
RunnerDep = Annotated[Runner, Depends(get_runner)]
ProviderDep = Annotated[assistant.Provider, Depends(get_provider)]


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
    board: list[dict] = []  # what the researcher pinned: title and text


class Question(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    view: View | None = None


class WorkspaceSummary(BaseModel):
    id: int
    name: str
    created: str
    updated: str


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


# Workspaces


def existing_workspace(store: Store, workspace_id: int) -> dict:
    workspace = store.workspace(workspace_id)
    if not workspace:
        raise HTTPException(404, "workspace not found")
    return workspace


@app.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceIn, store: StoreDep) -> WorkspaceSummary:
    workspace = store.create_workspace(body.name)
    return WorkspaceSummary(**{key: workspace[key] for key in WorkspaceSummary.model_fields})


@app.get("/workspaces")
def list_workspaces(store: StoreDep) -> list[WorkspaceSummary]:
    return store.workspaces()


@app.get("/workspaces/{workspace_id}")
def open_workspace(workspace_id: int, store: StoreDep) -> Workspace:
    """Everything in a workspace, including finished results, without recomputing."""
    workspace = existing_workspace(store, workspace_id)
    return Workspace(
        **workspace,
        areas=store.areas(workspace_id),
        jobs=[job_view(store, job) for job in store.jobs(workspace_id)],
    )


@app.patch("/workspaces/{workspace_id}")
def update_workspace(workspace_id: int, body: WorkspaceUpdate, store: StoreDep) -> Workspace:
    existing_workspace(store, workspace_id)
    store.update_workspace(workspace_id, body.name, body.settings)
    return open_workspace(workspace_id, store)


@app.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: int, store: StoreDep) -> Response:
    existing_workspace(store, workspace_id)
    store.delete_workspace(workspace_id)
    return Response(status_code=204)


# Areas


def existing_area(store: Store, area_id: int) -> dict:
    area = store.area(area_id)
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
    existing_area(store, area_id)
    store.delete_area(area_id)
    return Response(status_code=204)


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
    kind: Literal["experiment", "decomposition", "trend", "phenology", "lags", "correlation"]
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
    models: list[Literal["Ridge", "RandomForest", "XGBoost"]] = Field(
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
        store.save_result(key, found.to_dict())
    except ForecastError as exc:
        FAILED[key] = str(exc)
    except Exception as exc:  # noqa: BLE001 - any failure must reach the user, not vanish
        FAILED[key] = f"The models could not be fitted: {exc}"
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
        store.save_result(key, {**found.to_dict(), "area": response.area})
    except Exception as exc:  # noqa: BLE001 - any failure must reach the user, not vanish
        FAILED[key] = f"The models could not be explained: {exc}"
    finally:
        FITTING.discard(key)


def explanation_summary(stored: dict, area: str) -> list[str]:
    """The sentences are written when read, so that results explained earlier gain what the
    engine has learned to say since."""
    found = Explanation(
        stored["importance"],
        stored["families"],
        [Pair(**p) for p in stored["agreement"]],
        stored["seeds"],
        stored.get("family_range", {}),
        stored.get("dropped", {}),
    )
    return describe(stored.get("area", area), found)


def explanations_key(body: ModelsRequest, store: Store) -> str:
    return fingerprint({"explain": models_key(body, store), "with": "ranges and drop-column"})


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
        store.save_result(key, stability(response.area, X, y, params, test_start).to_dict())
    except Exception as exc:  # noqa: BLE001 - any failure must reach the user, not vanish
        FAILED[key] = f"Stability could not be checked: {exc}"
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
        return {"status": "done", **result}
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


@app.get("/workspaces/{workspace_id}/messages")
def list_messages(workspace_id: int, store: StoreDep) -> list[ChatMessage]:
    """The conversation with the assistant in this workspace, oldest first."""
    existing_workspace(store, workspace_id)
    return store.messages(workspace_id)


@app.delete("/workspaces/{workspace_id}/messages", status_code=204)
def clear_messages(workspace_id: int, store: StoreDep) -> Response:
    existing_workspace(store, workspace_id)
    store.clear_messages(workspace_id)
    return Response(status_code=204)


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
    context = [f"The researcher is on the {view.page} page."]
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
    # what the researcher pinned comes first: they chose it
    pinned = [
        facts.Fact(f"Board: {str(b.get('title', ''))[:80]}", str(b.get("text", ""))[:1500])
        for b in view.board[:20]
        if b.get("text")
    ]
    extra = pinned + forecast_facts(store, view, areas)
    return facts.View(context, series, view.charts, view.analyses, view.resolution, extra)


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
                found += [facts.Fact(card, line) for line in result["summary"]]
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
                found += [facts.Fact(card, line) for line in held["summary"]]
    return found


@app.post("/workspaces/{workspace_id}/chat")
def chat(
    workspace_id: int, body: Question, store: StoreDep, provider: ProviderDep
) -> StreamingResponse:
    """Ask the assistant. Events stream back as JSON lines and the answer is saved at the end.

    With a view of what is open, the assistant is given facts computed from the researcher's
    cached results. Events: view (the cards it was given), read (a closer look at a series),
    proposal (an analysis it proposes, which the researcher may add),
    text (a piece of the answer), search, search_failed, papers, check (the final answer after
    its citations were checked) and error.
    """
    existing_workspace(store, workspace_id)
    history = [{"role": m["role"], "content": m["content"]} for m in store.messages(workspace_id)]
    view = workspace_view(store, workspace_id, body.view) if body.view else None
    question = {"role": "user", "content": body.content}
    events = assistant.answer(provider, [*history, question], view=view)
    try:  # fail with a clear status before streaming starts, if the model cannot be reached
        first = next(events)
    except assistant.ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    store.add_message(workspace_id, "user", body.content)

    def stream() -> Iterator[str]:
        said, searches, papers, verdict, cards, reads, proposals = [], [], [], None, [], [], []
        try:
            for event in itertools.chain([first], events):
                match event["type"]:
                    case "text":
                        said.append(event["text"])
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
                yield json.dumps(event) + "\n"
        except assistant.ProviderError as exc:
            yield json.dumps({"type": "error", "message": f"The model stopped: {exc}"}) + "\n"
        finally:  # keep what was said, even if the reader left early
            details = {"searches": searches, "papers": papers, "cards": cards, "reads": reads}
            if proposals:
                details["proposals"] = proposals
            if verdict:
                details["check"] = {k: verdict[k] for k in ("cited", "removed", "unverified")}
                if "numbers" in verdict:
                    details["numbers"] = verdict["numbers"]
            text = verdict["text"] if verdict else "".join(said)
            store.add_message(workspace_id, "assistant", text, details)

    return StreamingResponse(stream(), media_type="application/x-ndjson")
