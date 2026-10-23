import sqlite3
from collections.abc import Iterator
from datetime import date
from functools import cache
from typing import Annotated, Literal

import engine
from engine import assistant
from engine.areas import AreaError, make_area
from engine.catalogue import CATALOGUE, get_variable
from engine.earth_engine import EarthEngineError, check
from engine.pipeline import Request
from engine.prepare import Resolution
from engine.series import Masking, band_name
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
    created: str


class Question(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


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


@app.post("/workspaces/{workspace_id}/chat")
def chat(
    workspace_id: int, body: Question, store: StoreDep, provider: ProviderDep
) -> StreamingResponse:
    """Ask the assistant. The answer streams back as plain text and is saved when complete."""
    existing_workspace(store, workspace_id)
    history = [{"role": m["role"], "content": m["content"]} for m in store.messages(workspace_id)]
    pieces = provider.stream([*history, {"role": "user", "content": body.content}])
    try:  # fail with a clear status before streaming starts, if the model cannot be reached
        first = next(pieces, "")
    except assistant.ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    store.add_message(workspace_id, "user", body.content)

    def answer() -> Iterator[str]:
        parts = [first]
        yield first
        try:
            for piece in pieces:
                parts.append(piece)
                yield piece
        except assistant.ProviderError as exc:
            parts.append(f"\n\n[The model stopped: {exc}]")
            yield parts[-1]
        finally:  # keep what was said, even if the reader left early
            store.add_message(workspace_id, "assistant", "".join(parts))

    return StreamingResponse(answer(), media_type="text/plain; charset=utf-8")
