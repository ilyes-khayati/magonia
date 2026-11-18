"""An explanation tested by trying to falsify what it implies, on the researcher's own series.

"NDVI falls with LST one month earlier" says more than that two series correlate. If LST
drives NDVI with that delay, then four things should be seen in the data:

1. linked: the anomalies correlate at the claimed lag, with the claimed sign;
2. beyond the response's memory: the link remains once last month's response anomaly is
   accounted for. A driver that merely follows vegetation (surface temperature rises when
   vegetation browns) shares the vegetation's memory and can seem to lead it;
3. in both halves of the record: the link passes in the first and in the second half alone;
4. not a shared trend: the link remains once a linear trend is removed from both series.

Each implication is a one-sided test (Fisher z), on the effective sample size of two
autocorrelated series (Bretherton et al. 1999), at alpha divided by the number of lags searched
(3 when the claim states a lag, matched within a month either side; 12 when it does not). The
explanation holds only if every implication passes: an intersection-union test, whose level is
alpha whatever the dependence between its parts (Berger and Hsu 1996, Statistical Science
11(4)). The logic is that of Popper's agentic falsification (Huang et al. 2025, arXiv
2502.09858), with a fixed, pre-registered set of implications in place of generated ones, so
that no language model decides what is tested; with a fixed set that must all hold, the
intersection-union test is exact, where merging e-values (Vovk and Wang 2021) would let one
strong implication carry a failed one.

Verdicts: holds (every implication passes), contradicted (the link passes with the opposite
sign), not shown (anything else; the implications that failed are named). The test plan and
its evaluation on simulated records were written before this module: evaluation/
falsification_plan.md.
"""

from dataclasses import asdict, dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from engine.lags import effective_n

ALPHA = 0.05
NEAR = 1  # months either side of a claimed lag
SEARCH = 12  # lags searched when the claim states none
NORMAL = NormalDist()


@dataclass
class Implication:
    name: str  # linked, memory, halves, trend
    words: str  # what it checks, for the researcher
    r: float | None
    p: float | None
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Falsification:
    verdict: str  # holds, contradicted, not shown, cannot test
    lag: int | None
    implications: list[Implication] = field(default_factory=list)
    level: float = ALPHA  # the per-test level after the lag correction

    @property
    def failed(self) -> list[Implication]:
        return [i for i in self.implications if not i.passed]

    def to_dict(self) -> dict:
        return {**asdict(self), "failed": [i.name for i in self.failed]}


def _pairs(y: pd.Series, x: pd.Series, lag: int) -> pd.DataFrame:
    """Each month's response with the driver `lag` months earlier, both present."""
    return pd.DataFrame({"y": y, "x": x.shift(lag)}).dropna()


def _r1(v: np.ndarray) -> float:
    """Lag-1 autocorrelation of a sequence, 0 when it cannot be computed."""
    if len(v) < 3 or np.std(v) == 0:
        return 0.0
    r = np.corrcoef(v[:-1], v[1:])[0, 1]
    return 0.0 if np.isnan(r) else float(r)


def _test(a: np.ndarray, b: np.ndarray, sign: int, controls: int = 0) -> tuple[float, float]:
    """Correlation of a and b and its one-sided p-value in the direction `sign`, on the
    effective sample size of the two sequences, less one per variable controlled for."""
    if len(a) < 12 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan"), 1.0
    r = float(np.corrcoef(a, b)[0, 1])
    n = effective_n(len(a), _r1(a), _r1(b)) - controls
    if n <= 4 or np.isnan(r):
        return r, 1.0
    z = float(np.arctanh(np.clip(r, -0.999999, 0.999999)) * np.sqrt(n - 3))
    return r, 1 - NORMAL.cdf(sign * z)


def _residual(v: np.ndarray, on: np.ndarray) -> np.ndarray:
    """v with the linear effect of `on` (and a constant) removed."""
    design = np.column_stack([np.ones(len(on)), on])
    coef, *_ = np.linalg.lstsq(design, v, rcond=None)
    return v - design @ coef


def falsify(
    y: pd.Series, x: pd.Series, sign: int, lag: int | None, alpha: float = ALPHA
) -> Falsification:
    """Try to falsify "the response follows the driver with this sign at this lag" on two
    monthly anomaly series indexed by month (deseasonalised beforehand, as lags.py does)."""
    window = list(range(max(1, lag - NEAR), lag + NEAR + 1)) if lag else list(range(1, SEARCH + 1))
    level = alpha / len(window)
    usable = {k: _pairs(y, x, k) for k in window}
    usable = {k: d for k, d in usable.items() if len(d) >= 24}
    if not usable:
        return Falsification("cannot test", lag, level=level)
    # the lag most favourable to the claim: the search is paid for by dividing alpha
    k = max(usable, key=lambda j: sign * np.corrcoef(usable[j]["y"], usable[j]["x"])[0, 1])
    d = usable[k]
    a, b = d["y"].to_numpy(), d["x"].to_numpy()

    out = []
    r, p = _test(a, b, sign)
    out.append(
        Implication("linked", f"linked {k} month{'s' if k > 1 else ''} earlier", r, p, p <= level)
    )

    prev = y.shift(1).reindex(d.index)
    ok = prev.notna().to_numpy()
    if ok.sum() >= 24:
        c = prev.to_numpy()[ok]
        rm, pm = _test(_residual(a[ok], c), _residual(b[ok], c), sign, controls=1)
    else:
        rm, pm = float("nan"), 1.0
    out.append(
        Implication(
            "memory", "beyond the response's own memory of the month before", rm, pm, pm <= level
        )
    )

    half = len(a) // 2
    r1, p1 = _test(a[:half], b[:half], sign)
    r2, p2 = _test(a[half:], b[half:], sign)
    out.append(
        Implication(
            "halves",
            "in both halves of the record",
            min(r1, r2, key=lambda v: sign * v) if not (np.isnan(r1) or np.isnan(r2)) else None,
            max(p1, p2),
            max(p1, p2) <= level,
            f"r = {r1:.2f} then {r2:.2f}",
        )
    )

    t = np.arange(len(a), dtype=float)
    rt, pt = _test(_residual(a, t), _residual(b, t), sign, controls=1)
    out.append(Implication("trend", "not a shared long-term trend", rt, pt, pt <= level))

    if all(i.passed for i in out):
        verdict = "holds"
    elif _test(a, b, -sign)[1] <= level:
        verdict = "contradicted"
    else:
        verdict = "not shown"
    return Falsification(verdict, k, out, level)


def lines(result: Falsification, response: str, driver: str) -> list[str]:
    """The test in words, implication by implication, for the researcher."""
    if result.verdict == "cannot test":
        return ["Too few months in common to test this explanation."]
    said = []
    for i in result.implications:
        mark = "passes" if i.passed else "fails"
        stat = f"r = {i.r:.2f}" if i.r is not None and not np.isnan(i.r) else "not computed"
        extra = f" ({i.detail})" if i.detail else ""
        said.append(f"{i.words.capitalize()}: {mark}, {stat}{extra}.")
    said.append(
        f"Each check is one-sided at {result.level:.3f} on the effective number of independent "
        "months; the explanation holds only if all four pass."
    )
    return said
