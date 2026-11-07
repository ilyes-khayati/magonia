"""Variables as images on the map: one month drawn as tiles, the value under a point, and the
pixels an area is averaged over."""

from dataclasses import dataclass

import ee

from engine.catalogue import Variable, get_variable
from engine.series import DERIVED, FILL, band_name, derived, flagged

# Viridis for amounts, brown to green for vegetation, blue to red for temperature, and red to
# blue around zero for drought: ramps that read the same for colour-blind eyes
VIRIDIS = ["440154", "414487", "2a788e", "22a884", "7ad151", "fde725"]
GREENNESS = ["8c510a", "bf812d", "dfc27d", "c7e9c0", "74c476", "238b45", "00441b"]
HEAT = ["313695", "4575b4", "abd9e9", "ffffbf", "fdae61", "f46d43", "a50026"]
DROUGHT = ["a50026", "f46d43", "fee090", "f7f7f7", "abd9e9", "4575b4", "313695"]


@dataclass(frozen=True)
class Legend:
    low: float
    high: float
    palette: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"low": self.low, "high": self.high, "palette": [f"#{c}" for c in self.palette]}


LEGENDS = {
    "ndvi": Legend(0.0, 0.9, tuple(GREENNESS)),
    "savi": Legend(0.0, 0.7, tuple(GREENNESS)),
    "evi": Legend(0.0, 0.6, tuple(GREENNESS)),
    "lai": Legend(0.0, 5.0, tuple(VIRIDIS)),
    "fpar": Legend(0.0, 1.0, tuple(VIRIDIS)),
    "gpp": Legend(0.0, 8.0, tuple(VIRIDIS)),
    "et": Legend(0.0, 5.0, tuple(VIRIDIS)),
    "ndmi": Legend(-0.4, 0.6, tuple(VIRIDIS)),
    "nbr": Legend(-0.2, 0.8, tuple(GREENNESS)),
    "lst": Legend(0.0, 50.0, tuple(HEAT)),
    "air_temperature": Legend(0.0, 35.0, tuple(HEAT)),
    "rain": Legend(0.0, 200.0, tuple(VIRIDIS)),
    "soil_moisture": Legend(0.0, 0.5, tuple(VIRIDIS)),
    "spei": Legend(-2.5, 2.5, tuple(DROUGHT)),
}


def legend(key: str) -> Legend:
    get_variable(key)  # unknown keys fail the same way everywhere
    return LEGENDS[key]


def in_units(key: str, variable: Variable, band: str, image: ee.Image) -> ee.Image:
    """One image in the variable's units, its flagged and fill pixels removed."""
    values = derived(key, image) if key in DERIVED else image.select(band)
    if key in FILL:
        values = values.updateMask(image.select(band).lte(FILL[key]))
    if variable.sampling != "centre" and key != "spei":
        values = values.updateMask(flagged(key, image).Not())
    scale = 1.0 if key in DERIVED else variable.scale
    return values.multiply(scale).add(variable.offset).rename("value")


def month_image(key: str, month: str, scale: int | None = None) -> ee.Image:
    """The mean of a variable's images in one month ("2020-03"), in its units."""
    variable = get_variable(key)
    band = band_name(variable, "pixel", scale)
    start = ee.Date(f"{month}-01")
    images = ee.ImageCollection(variable.collection).filterDate(start, start.advance(1, "month"))
    return images.map(lambda image: in_units(key, variable, band, image)).mean()


def tiles(key: str, month: str, scale: int | None = None) -> dict:
    """A tile URL template for one month of a variable, with the legend it is drawn with."""
    shown = legend(key)
    image = month_image(key, month, scale)
    found = image.getMapId({"min": shown.low, "max": shown.high, "palette": list(shown.palette)})
    return {"url": found["tile_fetcher"].url_format, "month": month, **shown.to_dict()}


def point_series(
    key: str, lon: float, lat: float, start: str, end: str, scale: int | None = None
) -> list[dict]:
    """The value of the pixel under a point, image by image, in the variable's units."""
    variable = get_variable(key)
    band = band_name(variable, "pixel", scale)
    point = ee.Geometry.Point([lon, lat])
    images = ee.ImageCollection(variable.collection).filterDate(start, end)

    def sample(image):
        value = in_units(key, variable, band, image).reduceRegion(
            ee.Reducer.first(), point, variable.pixel_m
        )
        return ee.Feature(
            None, {"date": image.date().format("YYYY-MM-dd"), "value": value.get("value")}
        )

    found = ee.FeatureCollection(images.map(sample)).getInfo()["features"]
    return [{"date": f["properties"]["date"], "value": f["properties"].get("value")} for f in found]


def pixel_grid(key: str, geometry: dict, limit: int = 2000) -> dict:
    """The outlines of the variable's own pixels that touch an area, as GeoJSON."""
    variable = get_variable(key)
    collection = ee.ImageCollection(variable.collection)
    projection = collection.first().select(0).projection().atScale(variable.pixel_m)
    area = ee.Geometry(geometry)
    cells = (
        ee.Image.pixelCoordinates(projection)
        .select("x")
        .multiply(1e6)
        .add(ee.Image.pixelCoordinates(projection).select("y"))
        .toInt64()
        .reproject(projection)
    )
    vectors = cells.reduceToVectors(
        geometry=area.buffer(variable.pixel_m / 2),
        crs=projection,
        geometryType="polygon",
        maxPixels=limit * 4,
        bestEffort=False,
    )
    return vectors.limit(limit).getInfo()
