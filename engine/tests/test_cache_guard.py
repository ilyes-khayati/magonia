"""Cached results are keyed by their request and engine.__version__ (api/jobs.py, the forecast
key in api/main.py). If the code that computes them changes and the version does not, Magonia
keeps serving results the old code computed, silently. This test notices such a change.

When it fails: if the change can alter a result (a value, a mask, a filled gap, a score), bump
engine.__version__ so that results are computed again; either way, copy the new hash below."""

import hashlib
from pathlib import Path

import engine

# The modules whose output is cached
COMPUTING = ["areas", "catalogue", "explain", "models", "pipeline", "prepare", "series"]

VERSION = "0.0.1"
HASH = "13953a6a35fe03ce"


def source_hash() -> str:
    folder = Path(engine.__file__).parent
    digest = hashlib.sha256()
    for name in COMPUTING:
        digest.update((folder / f"{name}.py").read_bytes())
    return digest.hexdigest()[:16]


def test_cached_results_cannot_outlive_the_code_that_computed_them():
    found = source_hash()
    assert (engine.__version__, found) == (VERSION, HASH), (
        f"The code behind cached results changed (hash {found}). If results can differ, bump "
        f"engine.__version__; then set VERSION = {engine.__version__!r} and HASH = {found!r} in "
        "this test."
    )
