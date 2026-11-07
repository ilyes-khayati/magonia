"""How much of each MODIS pixel is the crop the area is meant to be.

A 250 m pixel over a small orchard also sees the fields around it. Its NDVI is a mix, and an
area mean built from mixed pixels describes the mix, not the orchard. Following Lobell and
Asner (2004), each pixel's average year is split into two reference years: the most even one
nearby, as perennial cover such as trees keeps its leaves, and the most seasonal one, as an
annual crop greens in spring and is bare in summer. The share of the seasonal reference in
each pixel is its annual-crop share.

The references are taken from the pixels themselves (the flattest and the most seasonal
vegetated ones within a buffer), so no outside map is needed; they can only be as pure as the
purest pixels around.
"""

from dataclasses import asdict, dataclass

import ee
import numpy as np
from shapely.geometry import Point, shape

from engine.catalogue import get_variable
from engine.series import flagged

BUFFER_M = 1500
VEGETATED = 0.3  # a reference must average at least this NDVI: not bare soil, water or town
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class PurityError(ValueError):
    pass


@dataclass
class Purity:
    pixels: list[dict]  # lon, lat, crop share, amplitude, inside the area, fit error
    perennial: list[float]  # the reference years, by calendar month
    seasonal: list[float]
    area_cycle: list[float]  # the area's pixels' average year
    area_share: float  # mean annual-crop share of the pixels inside the area
    pixel_m: float
    summary: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def climatology(start: str, end: str) -> ee.Image:
    """MODIS NDVI averaged by calendar month over the years chosen: twelve bands."""
    variable = get_variable("ndvi")
    images = ee.ImageCollection(variable.collection).filterDate(start, end)

    def clean(image):
        return (
            image.select("NDVI")
            .updateMask(flagged("ndvi", image).Not())
            .multiply(variable.scale)
            .copyProperties(image, ["system:time_start"])
        )

    cleaned = images.map(clean)
    months = [
        cleaned.filter(ee.Filter.calendarRange(m, m, "month")).mean().rename(MONTHS[m - 1])
        for m in range(1, 13)
    ]
    return ee.Image.cat(months)


def sample(geometry: dict, start: str, end: str, buffer_m: int = BUFFER_M) -> list[dict]:
    """Each MODIS pixel within the buffer: its centre and its twelve monthly means."""
    variable = get_variable("ndvi")
    region = ee.Geometry(geometry).buffer(buffer_m)
    image = climatology(start, end)
    projection = ee.ImageCollection(variable.collection).first().select("NDVI").projection()
    points = image.reproject(projection).sample(
        region=region, projection=projection, geometries=True, dropNulls=True
    )
    found = points.limit(5000).getInfo()["features"]
    return [
        {
            "lon": f["geometry"]["coordinates"][0],
            "lat": f["geometry"]["coordinates"][1],
            "cycle": [f["properties"][m] for m in MONTHS],
        }
        for f in found
    ]


def unmix(cycle: np.ndarray, perennial: np.ndarray, seasonal: np.ndarray) -> tuple[float, float]:
    """The seasonal reference's share in a pixel's year, between 0 and 1, and the fit error."""
    d = seasonal - perennial
    share = float(np.clip(np.dot(cycle - perennial, d) / np.dot(d, d), 0, 1))
    fitted = perennial + share * d
    return share, float(np.sqrt(np.mean((cycle - fitted) ** 2)))


def purity(pixels: list[dict], geometry: dict, area: str, pixel_m: float = 231.7) -> Purity:
    """pixels: as sample() returns them; geometry: the area, to tell its own pixels apart."""
    if len(pixels) < 10:
        raise PurityError(f"{area}: only {len(pixels)} pixels with a full year around it.")
    cycles = np.array([p["cycle"] for p in pixels], dtype=float)
    amplitude = cycles.max(axis=1) - cycles.min(axis=1)
    vegetated = cycles.mean(axis=1) >= VEGETATED
    if vegetated.sum() < 2:
        raise PurityError(f"{area}: too few vegetated pixels around it to find references.")
    candidates = np.flatnonzero(vegetated)
    perennial = cycles[candidates[np.argmin(amplitude[candidates])]]
    seasonal = cycles[candidates[np.argmax(amplitude[candidates])]]

    shape_ = shape(geometry)
    # a pixel belongs to the area when its centre is inside, or within half a pixel of it
    near = shape_.buffer(pixel_m / 2 / 111_320)
    out = []
    for p, cycle, amp in zip(pixels, cycles, amplitude, strict=True):
        share, error = unmix(cycle, perennial, seasonal)
        out.append(
            {
                "lon": p["lon"],
                "lat": p["lat"],
                "share": round(share, 3),
                "amplitude": round(float(amp), 3),
                "error": round(error, 3),
                "inside": near.contains(Point(p["lon"], p["lat"])),
            }
        )
    own = [p for p in out if p["inside"]]
    if not own:
        raise PurityError(f"{area}: no pixel centre falls within half a pixel of it.")
    own_cycles = cycles[[i for i, p in enumerate(out) if p["inside"]]]
    share = float(np.mean([p["share"] for p in own]))
    return Purity(
        pixels=out,
        perennial=[round(float(v), 4) for v in perennial],
        seasonal=[round(float(v), 4) for v in seasonal],
        area_cycle=[round(float(v), 4) for v in own_cycles.mean(axis=0)],
        area_share=round(share, 3),
        pixel_m=pixel_m,
        summary=describe(area, own, share, perennial, seasonal, len(out)),
    )


def describe(area, own, share, perennial, seasonal, total) -> list[str]:
    worst = max(own, key=lambda p: p["share"])
    peak = MONTHS[int(np.argmax(seasonal))]
    mix = (
        f"{area}: its {len(own)} MODIS pixels are on average {share:.0%} annual crop and "
        f"{1 - share:.0%} perennial cover, measured against the most seasonal and the most even "
        f"vegetated pixels among {total} around it."
    )
    most = (
        f"{area}: the most mixed of its pixels is {worst['share']:.0%} annual crop "
        f"(at {worst['lat']:.4f}, {worst['lon']:.4f})."
    )
    references = (
        f"{area}: the seasonal reference peaks in {peak} and swings by "
        f"{seasonal.max() - seasonal.min():.2f} over the year; the even one swings by "
        f"{perennial.max() - perennial.min():.2f}."
    )
    lines = [mix, most, references]
    if perennial.max() - perennial.min() > 0.15:
        lines.append(
            f"{area}: even the most even pixel nearby swings by more than 0.15, so it is itself "
            "partly seasonal: the shares are relative to it, and the true crop share is higher."
        )
    if share >= 0.3:
        lines.append(
            f"{area}: with this much annual crop in its pixels, the area mean mixes the crop "
            "around it with the cover inside it; a finer sensor (Sentinel-2, 10 m) would "
            "separate them."
        )
    return lines
