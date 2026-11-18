"""The falsification test against the single test it refines, on records whose truth is known.

    uv run python evaluation/falsification_calibration.py OUT_DIR [--runs 1000]

The plan, written before the code and the first run, is evaluation/falsification_plan.md.
Monthly records of 300 months are made with a yearly cycle and anomalies that remember the
month before. The claim tested is always "the vegetation index falls with the driver one month
earlier", and five truths are simulated:

- S0 no link: driver and vegetation independent
- S1, S2 a real link at lag 1 of strength r = 0.25 and 0.35 between the anomalies
- S3 feedback: the driver follows this month's vegetation (as surface temperature rises when
  vegetation browns) and has no effect on it; the driver of last month then shares the
  vegetation's memory and seems to lead it
- S4 shared trend: both series drift over the 25 years in opposite directions, no link

For each, the share of records where the current test says "replicates" and where the
falsification test says "holds" is counted, with a 95% Monte Carlo interval (Wilson). Writes
OUT_DIR/falsification_calibration.md and .json.
"""

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

from engine.claims import Claim, lag_test
from engine.facts import Series, monthly_series
from engine.falsify import falsify
from engine.lags import deseasonalise

MONTHS = 300
RESPONSE_MEMORY = 0.6  # lag-1 autocorrelation of the vegetation anomalies
SCENARIOS = [
    # name, description, kind, parameters
    ("S0", "no link", "link", {"r": 0.0, "driver_memory": 0.8}),
    ("S1", "link r = 0.25 at lag 1", "link", {"r": 0.25, "driver_memory": 0.8}),
    ("S2", "link r = 0.35 at lag 1", "link", {"r": 0.35, "driver_memory": 0.8}),
    ("S3", "feedback: the driver follows vegetation, no effect on it", "feedback", {"c": 0.6}),
    ("S4", "shared trend, no link", "trend", {"drift": 1.5}),
]


def ar1(rng: np.random.Generator, n: int, phi: float) -> np.ndarray:
    x = np.zeros(n)
    x[0] = rng.normal()
    noise = rng.normal(size=n) * math.sqrt(1 - phi**2)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + noise[t]
    return x


def record(rng: np.random.Generator, kind: str, p: dict) -> tuple[np.ndarray, np.ndarray]:
    """Vegetation and driver anomalies (before the yearly cycle is added)."""
    if kind == "link":
        driver = ar1(rng, MONTHS + 1, p["driver_memory"])
        rest = ar1(rng, MONTHS, RESPONSE_MEMORY)
        # vegetation at month t falls with the driver at month t - 1
        veg = -p["r"] * driver[:MONTHS] + math.sqrt(1 - p["r"] ** 2) * rest
        return veg, driver[1:]
    if kind == "feedback":
        veg = ar1(rng, MONTHS, RESPONSE_MEMORY)
        own = ar1(rng, MONTHS, 0.5)
        # this month's driver follows this month's vegetation, and nothing else links them
        driver = -p["c"] * veg + math.sqrt(1 - p["c"] ** 2) * own
        return veg, driver
    if kind == "trend":
        ramp = np.linspace(-1, 1, MONTHS) * p["drift"]
        return ar1(rng, MONTHS, RESPONSE_MEMORY) + ramp, ar1(rng, MONTHS, 0.8) - ramp
    raise ValueError(kind)


def as_series(values: np.ndarray, key: str) -> Series:
    season = np.sin(2 * np.pi * (np.arange(MONTHS) % 12) / 12)
    dates = [date(2000 + m // 12, m % 12 + 1, 1).isoformat() for m in range(MONTHS)]
    level = 0.45 + 0.15 * season + 0.05 * values if key == "ndvi" else 30 + 8 * season + values
    pts = [
        {"date": d, "value": float(v), "masked": False} for d, v in zip(dates, level, strict=True)
    ]
    return Series("Synthetic", key, key.upper(), "", pts)


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z, ph = 1.96, k / n
    centre = (ph + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--runs", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261118)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    claim = Claim("synthetic", "lag", "ndvi", "lst", -1, "claim", 1)
    rows = []
    for name, words, kind, p in SCENARIOS:
        old = new = 0
        failed: dict[str, int] = {}
        for _ in range(args.runs):
            veg, drv = record(rng, kind, p)
            response, driver = as_series(veg, "ndvi"), as_series(drv, "lst")
            old += lag_test(claim, response, driver).verdict == "replicates"
            y = deseasonalise(monthly_series(response))
            x = deseasonalise(monthly_series(driver))
            result = falsify(y, x, -1, 1)
            new += result.verdict == "holds"
            for f in result.failed:
                failed[f.name] = failed.get(f.name, 0) + 1
        rows.append(
            {
                "scenario": name,
                "truth": words,
                "current_replicates": old / args.runs,
                "current_ci": wilson(old, args.runs),
                "new_holds": new / args.runs,
                "new_ci": wilson(new, args.runs),
                "failed_implications": {k: v / args.runs for k, v in sorted(failed.items())},
            }
        )
        print(name, f"current {old / args.runs:.3f}", f"new {new / args.runs:.3f}", failed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "falsification_calibration.json").write_text(json.dumps(rows, indent=1))
    lines = [
        f"# Falsification against the single test ({args.runs} simulated records per row, seed {args.seed})",
        "",
        "| Scenario | Truth | Current test: replicates (95% CI) | Falsification: holds (95% CI) | Implications that failed (share of records) |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        f = ", ".join(f"{k} {v:.0%}" for k, v in r["failed_implications"].items()) or "none"
        lines.append(
            f"| {r['scenario']} | {r['truth']} | {r['current_replicates']:.1%} "
            f"({r['current_ci'][0]:.1%}–{r['current_ci'][1]:.1%}) | {r['new_holds']:.1%} "
            f"({r['new_ci'][0]:.1%}–{r['new_ci'][1]:.1%}) | {f} |"
        )
    (args.out / "falsification_calibration.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
