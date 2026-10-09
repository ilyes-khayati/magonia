"""Connection to Google Earth Engine."""

import os

import ee
from dotenv import load_dotenv


class EarthEngineError(RuntimeError):
    """Raised when Earth Engine cannot be reached with the current settings."""


def connect(project: str | None = None) -> str:
    """Initialise Earth Engine and return the project used.

    The project comes from the argument, otherwise from EE_PROJECT in the
    environment or in a .env file.
    """
    load_dotenv()
    project = project or os.environ.get("EE_PROJECT")
    if not project:
        raise EarthEngineError(
            "No Earth Engine project set. Add EE_PROJECT to .env (see .env.example)."
        )
    try:
        ee.Initialize(project=project)
    except ee.EEException as exc:
        raise EarthEngineError(
            f"Could not connect to Earth Engine project '{project}'. "
            "Run `earthengine authenticate` and check that the project has Earth Engine enabled."
        ) from exc
    return project