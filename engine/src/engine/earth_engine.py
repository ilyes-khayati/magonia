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
            "No Earth Engine project is connected yet. Enter your project id to connect one."
        )
    try:
        ee.Initialize(project=project)
    except ee.EEException as exc:
        raise EarthEngineError(
            f"Could not connect to the Earth Engine project '{project}'. Check that this computer "
            "is signed in to Earth Engine and that the project has Earth Engine enabled."
        ) from exc
    return project


def check(project: str | None = None) -> str:
    """Connect and make one tiny request, so a wrong project is caught now, not mid-job."""
    project = connect(project)
    try:
        ee.Number(1).getInfo()
    except ee.EEException as exc:
        raise EarthEngineError(
            f"The Earth Engine project '{project}' did not answer. Check the project id."
        ) from exc
    return project


def plainly(exc: Exception, doing: str = "complete the request") -> str:
    """What an Earth Engine failure means for the researcher, without its internals."""
    text = str(exc).lower()
    if "quota" in text or "too many concurrent" in text or "rate" in text:
        return f"Earth Engine is busy and could not {doing}. Try again in a minute."
    if "timed out" in text or "memory" in text or "too many pixels" in text or "too large" in text:
        return (
            f"Earth Engine could not {doing}: the area or period is too large for one "
            "request. Try a smaller area or a shorter period."
        )
    if "permission" in text or "not authorized" in text or "credentials" in text:
        return f"Earth Engine refused to {doing}. Check the project's access to Earth Engine."
    if "no band" in text or "empty" in text or "0 bands" in text:
        return f"Earth Engine could not {doing}: there are no images for this choice."
    return f"Earth Engine could not {doing}. Try again; if it keeps failing, try a smaller area."
