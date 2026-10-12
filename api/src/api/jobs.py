"""Series requests run as background jobs, with results cached in the store."""

import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import engine
from engine.earth_engine import EarthEngineError, connect
from engine.pipeline import Request, Result, fingerprint, run
from engine.series import fetch

from api.store import Store


class Runner:
    """Runs jobs on a small pool of threads so requests never block the server."""

    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")

    def submit(self, work: Callable, *args) -> None:
        self.pool.submit(work, *args)


def cache_key(request: Request) -> str:
    """Identical requests on the same engine version share one cached result."""
    return fingerprint({"request": request.to_dict(), "engine": engine.__version__})


def number(value: float) -> float | None:
    return None if math.isnan(value) else float(value)


def to_response(result: Result, request: Request) -> dict:
    """The JSON the interface receives for a finished series."""
    variable = result.provenance["variable"]
    points = [
        {
            "date": row.date.date().isoformat(),
            "value": number(row.value),
            "sd": number(row.sd),
            "n_pixels": int(row.n_pixels),
            "masked": bool(row.masked),
            "filled": bool(row.filled),
            "n_obs": int(row.n_obs),
            "n_valid": int(row.n_valid),
        }
        for row in result.table.itertuples()
    ]
    name = f"{variable['name']}-{request.scale}" if request.scale else variable["name"]
    return {
        "variable": variable["key"],
        "name": name,
        "units": variable["units"],
        "points": points,
        "warnings": result.warnings,
        "provenance": result.provenance,
    }


def execute(store: Store, job_id: int, request: Request, key: str) -> None:
    """Run one job and record its result or a readable error."""
    store.set_job(job_id, "running")
    try:
        connect()
        result = run(request, fetch=fetch)
        store.save_result(key, to_response(result, request))
    except (EarthEngineError, ValueError) as exc:
        store.set_job(job_id, "failed", str(exc))
    except Exception as exc:  # noqa: BLE001 - any failure must reach the user, not vanish
        store.set_job(job_id, "failed", f"Earth Engine could not complete the request: {exc}")
    else:
        store.set_job(job_id, "done")
