"""Can Magon rediscover an unpublished finding from the data alone, and does it reason from the
data or from what it remembers about the place and the crop?

    uv run python evaluation/rediscovery.py RESULTS_DIR [--runs 3] [--regions Jendouba,Sfax]

The finding: at Jendouba, the MODIS "olive orchard" pixel greens up in winter and peaks in
March with a large yearly swing, which an evergreen olive canopy cannot do; the signal is that
of the herbaceous understory. It is not published, so no model can have read it. The answer key
(rediscovery_key.json, written by the researcher before any run) states it as short claims,
region by region.

The design follows FIRE-Bench (arXiv 2602.02905): the agent is given the question and the
scope, never the method or the conclusion, and each case is run several times because answers
vary from run to run. Each region is asked about twice, following epistemic blinding (arXiv
2604.06013): named ("Jendouba olive orchard") and blinded ("Site A", no crop, no place, no
workspace name). What differs between the two is what the model brings from memory.

The series are the researcher's own, read from the store of the running app
(~/.magonia/magonia.db) by the area each was extracted for: the same data they see. Each answer
is one line of RESULTS_DIR/raw.jsonl; scoring is done afterwards (rediscovery_score.py).
"""

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

from engine.assistant import Ollama, answer
from engine.facts import Series, View
from engine.library import Library

REGIONS = {  # area in km², as saved with each result, to find the region's series
    "Jendouba": 0.6446,
    "Sfax": 22.6472,
    "Zarzis": 19.4454,
    "Kairouan": 15.0257,
}
VARIABLES = ["ndvi", "spei", "lst"]
WINDOW = {"start": "2000-01-01", "end": "2026-01-01"}

# The same open question in both conditions: what to look at, never what to find
QUESTION = (
    "Look at the NDVI of {area} over the whole period: its average year, how far it swings "
    "within the year, and its trend. What kind of vegetation does this signal look like, and "
    "what could explain what you see?"
)


def series_of(db: sqlite3.Connection, km2: float) -> dict[str, dict]:
    """The latest monthly result of each variable extracted for the area of this size."""
    found: dict[str, dict] = {}
    for (response,) in db.execute("select response from results order by created"):
        r = json.loads(response)
        p = r.get("provenance", {})
        if r.get("variable") not in VARIABLES or p.get("window") != WINDOW:
            continue
        if abs(p.get("area", {}).get("area_km2", -1) - km2) > 0.001:
            continue
        if r["variable"] == "spei" and r.get("name") != "SPEI-3":
            continue
        found[r["variable"]] = r
    return found


def view_for(region: str, km2: float, results: dict[str, dict], blinded: bool, site: str) -> View:
    area = site if blinded else f"{region} olive orchard"
    series = [
        Series(area, key, r["name"], r["units"], r["points"], "monthly", r.get("warnings", []))
        for key, r in results.items()
    ]
    context = ["The researcher is on the charts page."]
    if not blinded:
        context.insert(0, 'The researcher is in the workspace "Orchards".')
    context += [
        f"Areas: {area} ({km2:.2f} km²).",
        "Period 2000-02 to 2025-12, monthly values, gaps of up to 2 filled.",
    ]
    analyses = [{"id": 1, "kind": "trend", "variable": "ndvi"}]
    return View(context, series, list(results), analyses)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--regions", default=",".join(REGIONS))
    parser.add_argument("--store", type=Path, default=Path.home() / ".magonia" / "magonia.db")
    args = parser.parse_args()

    provider = Ollama(
        os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434"),
        os.environ.get("MAGONIA_MODEL", "qwen2.5:7b"),
    )
    db = sqlite3.connect(args.store)
    args.results.mkdir(parents=True, exist_ok=True)
    library = Library(args.results / "papers.db", embed=provider.embed)
    raw = args.results / "raw.jsonl"
    done = set()
    if raw.exists():
        for line in raw.read_text().splitlines():
            r = json.loads(line)
            done.add((r["region"], r["condition"], r["run"]))

    for k, region in enumerate(args.regions.split(",")):
        km2 = REGIONS[region]
        results = series_of(db, km2)
        if "ndvi" not in results:
            print(f"{region}: no NDVI saved for {WINDOW}; extract it in Magonia first")
            continue
        for run in range(1, args.runs + 1):
            for condition in ("named", "blinded"):
                if (region, condition, run) in done:
                    continue
                site = f"Site {'ABCD'[k]}"
                view = view_for(region, km2, results, condition == "blinded", site)
                area = view.series[0].area
                question = QUESTION.format(area=area)
                record = {"region": region, "condition": condition, "run": run, "area": area}
                record |= {"question": question, "sheet": view.sheet(), "searches": []}
                start = time.time()
                for event in answer(
                    provider, [{"role": "user", "content": question}], view=view, library=library
                ):
                    if event["type"] == "route":
                        record["route"] = event["kind"]
                    elif event["type"] == "search":
                        record["searches"].append(event["query"])
                    elif event["type"] == "papers":
                        record.setdefault("papers", []).extend(
                            {"n": p["n"], "short": p["short"], "title": p["title"]}
                            for p in event["papers"]
                        )
                    elif event["type"] == "check":
                        record["check"] = event
                record["answer"] = record.get("check", {}).get("text", "")
                record["seconds"] = round(time.time() - start, 1)
                with raw.open("a") as out:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"{region} {condition} run {run}: {record['seconds']} s")


if __name__ == "__main__":
    main()
