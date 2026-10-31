"""Time series of satellite variables over an area."""

from typing import Literal

import ee
import pandas as pd

from engine.catalogue import Variable, get_variable

Masking = Literal["pixel", "date", "none"]
COLUMNS = ["date", "value", "sd", "n_pixels", "masked"]


# Stored values above these mark water, cities, barren land or no retrieval, never data
FILL = {"lai": 100, "fpar": 100, "gpp": 30000, "et": 32700}


def flagged(key: str, image: ee.Image) -> ee.Image:
    """1 where the variable's quality flag says the pixel should not be used."""
    if key in ("ndvi", "savi", "evi", "nbr"):
        # SummaryQA: 0 good, 1 marginal, 2 snow or ice, 3 cloudy
        return image.select("SummaryQA").gte(2)
    if key == "lst":
        # QC_Day bits 6-7: LST error 0 (<= 1 K), 1 (<= 2 K), 2 (<= 3 K), 3 (> 3 K)
        return image.select("QC_Day").rightShift(6).bitwiseAnd(3).gte(2)
    if key in ("lai", "fpar"):
        # FparLai_QC bits 5-7: 0 or 1 main algorithm, 2 or 3 backup, 4 not retrieved
        backup = image.select("FparLai_QC").rightShift(5).bitwiseAnd(7).gte(2)
        return backup.Or(image.select(get_variable(key).band).gt(FILL[key]))
    if key in ("gpp", "et"):
        return image.select(get_variable(key).band).gt(FILL[key])
    if key == "ndmi":
        # StateQA bits 0-1: cloud state 0 clear, 1 cloudy, 2 mixed, 3 assumed clear; bit 2 shadow
        state = image.select("StateQA")
        cloud = state.bitwiseAnd(3)
        return cloud.eq(1).Or(cloud.eq(2)).Or(state.rightShift(2).bitwiseAnd(1).eq(1))
    raise ValueError(f"no quality rule for {key}")


def series(
    key: str,
    geometry: dict,
    start: str,
    end: str,
    masking: Masking = "pixel",
    scale: int | None = None,
) -> pd.DataFrame:
    """A variable from the catalogue over a GeoJSON geometry, one row per image.

    masking chooses how flagged observations are removed: "pixel" drops
    flagged pixels and averages the rest, "date" drops the whole date when
    half the area or more is flagged, "none" keeps everything.
    scale is the accumulation period in months, for multi-scale indices such as SPEI.
    """
    features = fetch(key, geometry, start, end, masking, scale)
    return to_table(features, get_variable(key), masking)


def band_name(variable: Variable, masking: Masking, scale: int | None) -> str:
    """Check the options for a variable and return the band to extract."""
    if masking not in ("pixel", "date", "none"):
        raise ValueError(f"masking must be 'pixel', 'date' or 'none', not {masking!r}")
    if variable.scales:
        return variable.band.format(scale=check_scale(variable, scale))
    if scale is not None:
        raise ValueError(f"{variable.name} has no time scale")
    return variable.band


def fetch(
    key: str, geometry: dict, start: str, end: str, masking: Masking, scale: int | None
) -> list[dict]:
    """Ask Earth Engine for one feature per image, with the area's statistics."""
    variable = get_variable(key)
    band = band_name(variable, masking, scale)

    area = ee.Geometry(geometry)
    images = ee.ImageCollection(variable.collection).filterDate(start, end)

    if variable.sampling == "centre":
        centre = area.centroid(maxError=1)

        def sample(image):
            value = image.select(band).reduceRegion(ee.Reducer.first(), centre, variable.pixel_m)
            return ee.Feature(
                None,
                {
                    "date": image.date().format("YYYY-MM-dd"),
                    "value": value.get(band),
                    "n_pixels": 1,
                },
            )

        return ee.FeatureCollection(images.map(sample)).getInfo()["features"]

    stats = (
        ee.Reducer.mean()
        .combine(ee.Reducer.stdDev(), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )

    def summarise(image):
        bad = flagged(key, image)
        values = derived(key, image) if key in DERIVED else image.select(band)
        if key in FILL:
            # fill values are never data, whatever the cloud filter
            values = values.updateMask(image.select(band).lte(FILL[key]))
        if masking == "pixel":
            values = values.updateMask(bad.Not())
        result = values.reduceRegion(stats, area, scale=variable.pixel_m)
        share_flagged = bad.reduceRegion(ee.Reducer.mean(), area, scale=variable.pixel_m)
        return ee.Feature(
            None,
            {
                "date": image.date().format("YYYY-MM-dd"),
                "value": result.get(f"{band}_mean"),
                "sd": result.get(f"{band}_stdDev"),
                "n_pixels": result.get(f"{band}_count"),
                "flagged": share_flagged.values().get(0),
            },
        )

    return ee.FeatureCollection(images.map(summarise)).getInfo()["features"]


DERIVED = {"savi", "ndmi", "nbr"}


def normalised_difference(a: ee.Image, b: ee.Image) -> ee.Image:
    return a.subtract(b).divide(a.add(b))


def derived(key: str, image: ee.Image) -> ee.Image:
    """A band computed from reflectances, which MODIS stores scaled by 10 000."""

    def band(name: str) -> ee.Image:
        return image.select(name).multiply(0.0001)

    if key == "savi":
        red, nir = band("sur_refl_b01"), band("sur_refl_b02")
        return nir.subtract(red).multiply(1.5).divide(nir.add(red).add(0.5)).rename("SAVI")
    if key == "ndmi":
        return normalised_difference(band("sur_refl_b02"), band("sur_refl_b06")).rename("NDMI")
    if key == "nbr":
        return normalised_difference(band("sur_refl_b02"), band("sur_refl_b07")).rename("NBR")
    raise ValueError(f"{key} is not computed")


def check_scale(variable: Variable, scale: int | None) -> int:
    """The time scale in months, which multi-scale indices such as SPEI require."""
    if scale is None or not 1 <= scale <= 48:
        raise ValueError(f"{variable.name} needs a time scale between 1 and 48 months")
    return scale


def to_table(features: list[dict], variable: Variable, masking: Masking = "pixel") -> pd.DataFrame:
    """Turn Earth Engine features into one row per date, in the variable's units.

    A date is masked when it has no usable value: every pixel was flagged, the
    whole date was dropped, or Earth Engine returned nothing.
    """
    table = pd.DataFrame(
        [f["properties"] for f in features], columns=["date", "value", "sd", "n_pixels", "flagged"]
    )
    table["date"] = pd.to_datetime(table["date"])
    table["value"] = pd.to_numeric(table["value"]) * variable.scale + variable.offset
    table["sd"] = pd.to_numeric(table["sd"]) * variable.scale
    table["n_pixels"] = pd.to_numeric(table["n_pixels"]).fillna(0).astype(int)
    table.loc[table["value"].isna(), "n_pixels"] = 0

    if masking == "date" and variable.sampling == "mean":
        dropped = pd.to_numeric(table["flagged"]) >= 0.5
        table.loc[dropped, ["value", "sd"]] = float("nan")
        table.loc[dropped, "n_pixels"] = 0

    table["masked"] = table["value"].isna()
    return table[COLUMNS]


def size_warnings(variable: Variable, area_km2: float) -> list[str]:
    """Warn when the area is smaller than one pixel of the variable."""
    if variable.sampling == "centre":
        warning = (
            f"{variable.name} is read from the {variable.resolution} grid cell "
            f"(about {variable.pixel_m / 1000:.0f} km across) that contains the centre of this "
            "area, so every field in that cell has the same value."
        )
        return [warning]
    pixel_km2 = (variable.pixel_m / 1000) ** 2
    if area_km2 >= pixel_km2:
        return []
    warning = (
        f"This area ({area_km2:.2f} km²) is smaller than one {variable.resolution} pixel "
        f"of {variable.name}, so its values include the surroundings."
    )
    return [warning]
