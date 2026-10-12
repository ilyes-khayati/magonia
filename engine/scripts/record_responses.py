"""Record Earth Engine's responses for the acceptance cases, so CI can replay them.

Run from engine/ after the extraction code changes:  uv run python scripts/record_responses.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

from acceptance_cases import CASES, RECORDED, orchard

from engine.earth_engine import connect
from engine.series import fetch

connect()
RECORDED.mkdir(exist_ok=True)
for name, case in CASES.items():
    features = fetch(case.variable, orchard(), case.start, case.end, case.masking, case.scale)
    path = RECORDED / f"{name}.json"
    path.write_text(json.dumps(features, separators=(",", ":")))
    print(f"{name}: {len(features)} images -> {path.name}")
