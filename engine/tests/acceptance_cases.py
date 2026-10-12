"""The reference cases: the 2026 paper's extraction for the Jendouba orchard."""

import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).parent / "data"
RECORDED = DATA / "recorded"
START, END = "2000-03-01", "2025-01-01"


@dataclass(frozen=True)
class Case:
    variable: str
    masking: str
    reference: str  # CSV in tests/data
    column: str
    scale: int | None = None
    start: str = START
    end: str = END


CASES = {
    "ndvi": Case("ndvi", "date", "reference_ndvi_16day.csv", "NDVI"),
    "lst": Case("lst", "none", "reference_lst_8day.csv", "LST"),
    **{
        f"spei_{scale}": Case("spei", "none", "reference_spei_monthly.csv", f"SPEI_{scale}", scale)
        for scale in (1, 3, 6, 12, 24, 48)
    },
}


def orchard() -> dict:
    return json.loads((DATA / "jendouba_orchard.geojson").read_text())["features"][0]["geometry"]
