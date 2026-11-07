"""Wavelet coherence: where in time, and at which periods, two series move together.

A Pearson coefficient gives one number for the whole record. Coherence gives one for every
month and every period, so that a link present only in the annual cycle, or only after a
change of management, can be seen. The phase between the two says which leads.

Continuous Morlet transform as Torrence and Compo (1998); coherence smoothed in time and scale
as Grinsted, Moore and Jevrejeva (2004); significance against two red-noise series with the
same lag-1 autocorrelations, by Monte Carlo.
"""

from dataclasses import asdict, dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

OMEGA = 6.0  # Morlet centre frequency
FOURIER = 4 * np.pi / (OMEGA + np.sqrt(2 + OMEGA**2))  # scale to Fourier period
DJ = 1 / 8  # scales per octave: eight
MIN_MONTHS = 36


class CoherenceError(ValueError):
    pass


@dataclass
class Coherence:
    times: list[str]  # "YYYY-MM"
    periods: list[float]  # months
    coherence: list[list[float]]  # [period][time], 0 to 1
    phase: list[
        list[float]
    ]  # [period][time], radians: 0 together, π opposite, +π/2 the first leads
    significant: list[list[bool]]  # [period][time], above the 95% red-noise level
    coi: list[float]  # by time: the longest period not distorted by the record's ends
    summary: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def scales(n: int) -> np.ndarray:
    """From two months to a third of the record, eight scales per octave."""
    s0 = 2 / FOURIER
    top = int(np.log2(n / 3 / 2) / DJ)
    return s0 * 2 ** (DJ * np.arange(top + 1))


def cwt(x: np.ndarray, s: np.ndarray) -> np.ndarray:
    """The Morlet transform of x, one row per scale, computed by FFT (Torrence and Compo)."""
    n = len(x)
    pad = 2 ** int(np.ceil(np.log2(n)) + 1)
    k = 2 * np.pi * np.fft.fftfreq(pad)
    xf = np.fft.fft(x - x.mean(), pad)
    rows = []
    for scale in s:
        daughter = (
            np.pi**-0.25 * np.sqrt(2 * np.pi * scale) * np.exp(-((scale * k - OMEGA) ** 2) / 2)
        )
        daughter[k <= 0] = 0
        rows.append(np.fft.ifft(xf * daughter)[:n])
    return np.array(rows)


def smooth(w: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Smoothing in time (Gaussian, width the scale) and scale (0.6 of an octave), Grinsted."""
    n = w.shape[1]
    k = 2 * np.pi * np.fft.fftfreq(n)
    out = np.empty(w.shape, dtype=complex)
    for i, scale in enumerate(s):
        out[i] = np.fft.ifft(np.fft.fft(w[i]) * np.exp(-0.5 * (scale * k) ** 2))
    width = max(1, round(0.6 / DJ))
    kernel = np.ones(width) / width
    for t in range(n):
        out[:, t] = np.convolve(out[:, t], kernel, mode="same")
    return out


def coherence_of(x: np.ndarray, y: np.ndarray, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    wx, wy = cwt(x, s), cwt(y, s)
    sx = smooth(np.abs(wx) ** 2 / s[:, None], s)
    sy = smooth(np.abs(wy) ** 2 / s[:, None], s)
    sxy = smooth(wx * np.conj(wy) / s[:, None], s)
    r2 = np.abs(sxy) ** 2 / (sx.real * sy.real)
    return np.clip(r2.real, 0, 1), np.angle(sxy)


def ar1(x: np.ndarray) -> float:
    a = x - x.mean()
    return float(np.clip(np.sum(a[1:] * a[:-1]) / np.sum(a * a), 0, 0.99))


def red_noise(n: int, alpha: float, rng: np.random.Generator) -> np.ndarray:
    out = np.empty(n)
    out[0] = rng.normal()
    for t in range(1, n):
        out[t] = alpha * out[t - 1] + rng.normal()
    return out


def significance(
    n: int, ax: float, ay: float, s: np.ndarray, runs: int = 200, seed: int = 0
) -> np.ndarray:
    """The 95th percentile of coherence between two red noises, by scale."""
    rng = np.random.default_rng(seed)
    edge = max(1, n // 6)  # away from the ends, where the cone of influence hides it anyway
    found = []
    for _ in range(runs):
        r2, _ = coherence_of(red_noise(n, ax, rng), red_noise(n, ay, rng), s)
        found.append(r2[:, edge:-edge])
    # every value of every run, by scale: what coherence noise alone reaches 5% of the time
    return np.percentile(np.concatenate(found, axis=1), 95, axis=1)


def regular(points: pd.Series) -> pd.Series:
    """Monthly, with short gaps filled by straight lines; the transform needs every month."""
    monthly = points.asfreq("MS")
    return monthly.interpolate(limit=3, limit_area="inside")


def longest_run(frame: pd.DataFrame) -> pd.DataFrame:
    """The longest stretch of consecutive months."""
    if frame.empty:
        return frame
    months = frame.index.year * 12 + frame.index.month
    breaks = np.concatenate([[0], np.flatnonzero(np.diff(months) != 1) + 1, [len(frame)]])
    start, stop = max(pairwise(breaks), key=lambda pair: pair[1] - pair[0])
    return frame.iloc[start:stop]


def coherence(
    a: pd.Series, b: pd.Series, a_title: str, b_title: str, area: str, runs: int = 200
) -> Coherence:
    """a and b: monthly values indexed by month start. The months both have are used."""
    both = longest_run(pd.concat([regular(a), regular(b)], axis=1).dropna())
    if len(both) < MIN_MONTHS:
        raise CoherenceError(
            f"{area}: {a_title} and {b_title} share {len(both)} consecutive months; wavelet "
            f"coherence needs at least {MIN_MONTHS}."
        )
    x = both.iloc[:, 0].to_numpy(float)
    y = both.iloc[:, 1].to_numpy(float)
    x = (x - x.mean()) / (x.std() or 1)
    y = (y - y.mean()) / (y.std() or 1)
    n = len(x)
    s = scales(n)
    r2, phase = coherence_of(x, y, s)
    level = significance(n, ar1(x), ar1(y), s, runs)
    periods = s * FOURIER
    edge = np.minimum(np.arange(1, n + 1), np.arange(n, 0, -1))
    coi = FOURIER / np.sqrt(2) * edge

    return Coherence(
        times=[f"{t:%Y-%m}" for t in both.index],
        periods=[round(float(p), 3) for p in periods],
        coherence=np.round(r2, 3).tolist(),
        phase=np.round(phase, 3).tolist(),
        significant=(r2 > level[:, None]).tolist(),
        coi=[round(float(c), 3) for c in coi],
        summary=describe(
            area, a_title, b_title, r2, phase, r2 > level[:, None], periods, coi, both.index
        ),
    )


def describe(area, a_title, b_title, r2, phase, significant, periods, coi, index) -> list[str]:
    """Plain sentences: the annual band, and the other periods where the link holds."""
    inside = periods[:, None] <= coi[None, :]
    lines = []
    annual = np.argmin(np.abs(periods - 12))
    row = inside[annual]
    if row.any():
        share = significant[annual][row].mean()
        mean_r2 = r2[annual][row].mean()
        # the mean phase as a lead in months at the annual period
        angle = (
            np.angle(np.mean(np.exp(1j * phase[annual][row & significant[annual]])))
            if (row & significant[annual]).any()
            else np.nan
        )
        lines.append(
            f"{area}: at the annual period, {a_title} and {b_title} are coherent "
            f"{share:.0%} of the time inside the cone (mean coherence {mean_r2:.2f})."
        )
        if not np.isnan(angle):
            months = angle / (2 * np.pi) * 12
            if abs(angle) > 5 * np.pi / 6:
                relation = "move in opposite directions"
            elif abs(angle) < np.pi / 6:
                relation = "move together"
            else:
                relation = f"are out of step by about {abs(months):.1f} months"
            lead = (
                ""
                if abs(angle) < np.pi / 6 or abs(angle) > 5 * np.pi / 6
                else f", {a_title if angle > 0 else b_title} leading"
            )
            lines.append(f"{area}: where significant at that period, they {relation}{lead}.")
    bands = []
    for i, p in enumerate(periods):
        # the annual band spreads over neighbouring periods; those are said above
        if 8 <= p <= 18 or not inside[i].any():
            continue
        share = significant[i][inside[i]].mean()
        if share >= 0.25:
            bands.append((p, share))
    if bands:
        listed = ", ".join(
            f"{p:.0f} months ({share:.0%})" for p, share in bands[:: max(1, len(bands) // 4)][:4]
        )
        lines.append(f"{area}: coherence beyond red noise also at {listed} of the time.")
    else:
        lines.append(
            f"{area}: no period other than the annual one is coherent beyond red noise for long."
        )
    return lines
