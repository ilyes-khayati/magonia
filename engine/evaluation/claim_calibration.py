"""How often claim testing gives the right verdict, on orchards whose truth is known.

    uv run python evaluation/claim_calibration.py OUT_DIR [--runs 500]

On real data nobody knows whether a claim is true, so a verdict cannot be scored there. Here
monthly series are made with the shape of the reference orchard's (25 years, a yearly cycle,
anomalies that remember the months before) and a link put in on purpose: none, or the driver
acting on vegetation at a known lag, with a known strength and sign. Each is tested as a
researcher would, and the verdicts are counted:

- with no link, how often the claim is said to replicate (false replication; the bound is
  meant to keep it near or under 5%) or to be contradicted
- with a link at the claimed lag, how often it replicates (power), at several strengths
- with the opposite sign, how often it is contradicted
- with the link at another lag than the one claimed, how often the claimed lag replicates:
  a driver that remembers its own past (SPEI does) spreads a link over neighbouring lags

Strength is given as the correlation the link would have between the two anomaly series, the
number a researcher reads off the lag explorer. Writes OUT_DIR/claim_calibration.md and .json.
"""

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from engine.claims import Claim, lag_test
from engine.facts import Series

MONTHS = 300  # 2000 to 2024, as the reference orchard
DRIVER_MEMORY = 0.8  # lag-1 autocorrelation of SPEI-like anomalies
RESPONSE_MEMORY = 0.6  # of NDVI anomalies left after the link
CLAIMED_LAG = 6
SINGLE = False  # --single: the single correlation test that ADR 0025 replaced


def ar1(rng: np.random.Generator, n: int, phi: float) -> np.ndarray:
    x = np.zeros(n)
    noise = rng.normal(size=n) * np.sqrt(1 - phi**2)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + noise[t]
    return x


def orchard(rng: np.random.Generator, r: float, lag: int) -> tuple[Series, Series]:
    """A driver and a vegetation series whose anomalies correlate by r at the given lag."""
    season = np.sin(2 * np.pi * (np.arange(MONTHS) % 12) / 12)
    driver = ar1(rng, MONTHS + lag, DRIVER_MEMORY)
    linked = driver[:MONTHS] if lag else driver[lag:]  # the driver lag months earlier
    rest = ar1(rng, MONTHS, RESPONSE_MEMORY)
    anomaly = r * linked + np.sqrt(max(1 - r**2, 0)) * rest
    response = 0.45 + 0.15 * season + 0.05 * anomaly
    spei = driver[lag:] + 0.3 * season
    dates = [date(2000 + m // 12, m % 12 + 1, 1).isoformat() for m in range(MONTHS)]

    def points(values: np.ndarray) -> list[dict]:
        return [
            {"date": d, "value": float(v), "masked": False}
            for d, v in zip(dates, values, strict=True)
        ]

    return (
        Series("Synthetic", "ndvi", "NDVI", "", points(response)),
        Series("Synthetic", "spei", "SPEI-12", "", points(spei)),
    )


def verdicts(rng, runs: int, r: float, lag: int, claimed_sign: int) -> dict[str, float]:
    claim = Claim("synthetic", "lag", "ndvi", "spei", claimed_sign, "claim", CLAIMED_LAG)
    counts: dict[str, int] = {}
    for _ in range(runs):
        response, driver = orchard(rng, r, lag)
        verdict = lag_test(claim, response, driver, single=SINGLE).verdict
        counts[verdict] = counts.get(verdict, 0) + 1
    return {v: counts.get(v, 0) / runs for v in ("replicates", "contradicts", "undecided")}


SCENARIOS = [
    # name, true correlation at the true lag, true lag, claimed sign
    ("no link", 0.0, CLAIMED_LAG, 1),
    ("link r = 0.15 at the claimed lag", 0.15, CLAIMED_LAG, 1),
    ("link r = 0.25 at the claimed lag", 0.25, CLAIMED_LAG, 1),
    ("link r = 0.35 at the claimed lag", 0.35, CLAIMED_LAG, 1),
    ("link r = 0.35, opposite to the claim", -0.35, CLAIMED_LAG, 1),
    ("link r = 0.35 at lag 2, claim says 6", 0.35, 2, 1),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--single", action="store_true", help="the single test ADR 0025 replaced")
    args = parser.parse_args()
    global SINGLE
    SINGLE = args.single
    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    results = {}
    for name, r, lag, sign in SCENARIOS:
        results[name] = verdicts(rng, args.runs, r, lag, sign)
        print(name, results[name], flush=True)
    lines = [
        "# Claim testing on orchards with a known truth",
        "",
        (
            f"{args.runs} synthetic orchards per row, 300 months each; the claim tested is "
            f'"NDVI rises with SPEI {CLAIMED_LAG} months earlier". Driver memory '
            f"{DRIVER_MEMORY}, vegetation memory {RESPONSE_MEMORY} (lag-1 autocorrelation)."
        ),
        "",
        "| Truth | Replicates | Contradicts | Undecided |",
        "|---|---|---|---|",
    ]
    for name, share in results.items():
        lines.append(
            f"| {name} | {share['replicates']:.1%} | {share['contradicts']:.1%} | "
            f"{share['undecided']:.1%} |"
        )
    (args.out / "claim_calibration.md").write_text("\n".join(lines) + "\n")
    (args.out / "claim_calibration.json").write_text(json.dumps(results, indent=1))
    print(args.out / "claim_calibration.md")


if __name__ == "__main__":
    main()
