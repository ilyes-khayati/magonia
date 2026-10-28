"""Which past months of a variable, and of its drivers, carry information about it.

The method of the 2026 paper (notebook 03). The response's memory of itself is read from
its autocorrelation. A driver is correlated with the response at lags of 1 to 12 months,
and a lag stands out only if it passes a bound that accounts for two things a plain
1.96/√n band ignores: neighbouring months are not independent, so the effective sample size
is smaller (Bretherton et al., 1999), and the best of twelve lags is being picked, so the
level is Bonferroni corrected. A lag that stands out with the opposite sign to the physical
expectation is reported as such, not as a finding.

Series are monthly, indexed by month start. By default each is first deseasonalised, so
that a shared yearly cycle is not mistaken for a link. The paper goes one step further and
correlates drivers with what the response's own history leaves unexplained; that needs a
fitted model of the response and comes with the models.
"""

from dataclasses import asdict, dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

MAX_OWN_LAG = 24
MAX_DRIVER_LAG = 12
ALPHA = 0.05

# The sign a physically plausible link with vegetation has: hotter than usual is less green,
# wetter than usual (higher SPEI) is greener
EXPECTED = {"lst": -1, "spei": +1}


def deseasonalise(series: pd.Series) -> pd.Series:
    """Each month minus the average of its calendar month."""
    return series - series.groupby(series.index.month).transform("mean")


def acf(series: pd.Series, max_lag: int = MAX_OWN_LAG) -> list[float]:
    """Autocorrelation at lags 1 to max_lag, as in the paper. Each month is paired only with
    the month really k earlier, so that empty months (snow, cloud) do not join the months on
    either side; without gaps this is the paper's formula exactly."""
    v = series - series.mean()
    return [float((v * v.shift(k)).sum() / (v * v).sum()) for k in range(1, max_lag + 1)]


def effective_n(n: int, r1a: float, r1b: float) -> float:
    """Effective sample size of two autocorrelated series (Bretherton et al., 1999)."""
    return n * (1 - r1a * r1b) / (1 + r1a * r1b)


def bound(response: pd.Series, driver: pd.Series, lags: int = MAX_DRIVER_LAG) -> float:
    """The |r| a lag must exceed to stand out: 5%, two-sided, Bonferroni over the lags."""
    z = NormalDist().inv_cdf(1 - ALPHA / (2 * lags))
    n = effective_n(int(response.notna().sum()), response.autocorr(1), driver.autocorr(1))
    return float(z / np.sqrt(n))


@dataclass
class Evidence:
    driver: str
    r: list[float]  # at lags 1 to 12, the driver leading
    bound: float
    lag: int  # the strongest
    best: float
    expected: int | None  # the plausible sign, if known
    decision: str = field(init=False)

    def __post_init__(self) -> None:
        if abs(self.best) <= self.bound:
            self.decision = "not significant"
        elif self.expected is not None and np.sign(self.best) != self.expected:
            self.decision = "implausible sign"
        else:
            self.decision = "stands out"

    def to_dict(self) -> dict:
        return asdict(self)


def driver_evidence(
    response: pd.Series, driver: pd.Series, name: str, key: str, max_lag: int = MAX_DRIVER_LAG
) -> Evidence:
    """Correlation of the response with the driver 1 to max_lag months earlier."""
    r = [
        float(response.corr(driver.shift(lag).reindex(response.index)))
        for lag in range(1, max_lag + 1)
    ]
    best = int(np.nanargmax(np.abs(r)))
    return Evidence(name, r, bound(response, driver, max_lag), best + 1, r[best], EXPECTED.get(key))


@dataclass
class Exploration:
    acf: list[float]  # the response at lags 1 to 24
    acf_band: float  # 1.96/√n: what chance alone gives a single lag
    drivers: list[Evidence]
    summary: list[str]

    def to_dict(self) -> dict:
        return {
            "acf": self.acf,
            "acf_band": self.acf_band,
            "drivers": [d.to_dict() for d in self.drivers],
            "summary": self.summary,
        }


def explore(
    area: str,
    response: tuple[str, str, pd.Series],
    drivers: list[tuple[str, str, pd.Series]],
    deseasonalise_first: bool = True,
) -> Exploration:
    """Memory and driver lags of a monthly response; each series is (title, key, values)."""
    title, _, y = response
    if deseasonalise_first:
        y = deseasonalise(y)
    what = "anomalies" if deseasonalise_first else "values"
    memory = acf(y)
    band = float(1.96 / np.sqrt(y.notna().sum()))
    standing = [k + 1 for k, r in enumerate(memory) if abs(r) > band]
    if standing:
        strongest = max(standing[1:] or standing, key=lambda k: abs(memory[k - 1]))
        later = f", and most beyond that at {strongest} months (r = {memory[strongest - 1]:.2f})"
        first = (
            f"{area}: {title} {what} remember themselves at {len(standing)} of 24 lags beyond chance "
            f"(±{band:.2f}); at 1 month r = {memory[0]:.2f}{later if strongest != 1 else ''}."
        )
        summary = [first]
    else:
        summary = [
            f"{area}: {title} {what} show no memory of themselves beyond chance (±{band:.2f})."
        ]

    evidence = []
    for name, key, x in drivers:
        if deseasonalise_first:
            x = deseasonalise(x)
        found = driver_evidence(y, x, name, key)
        evidence.append(found)
        when = f"{found.lag} month{'s' if found.lag > 1 else ''} earlier"
        stats = f"r = {found.best:.2f}, bound ±{found.bound:.2f}"
        if found.decision == "stands out":
            plausible = " with the expected sign" if found.expected is not None else ""
            verdict = f"stands out{plausible}"
        elif found.decision == "implausible sign":
            verdict = (
                "is beyond its bound but with the opposite sign to the physical expectation, so it "
                "is not taken as a link"
            )
        else:
            verdict = "does not stand out from chance"
        summary.append(
            f"{area}: {name} {when} is the strongest of lags 1 to 12 ({stats}); it {verdict}."
        )
    return Exploration(memory, band, evidence, summary)
