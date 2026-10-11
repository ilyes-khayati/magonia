"""Named areas: load GeoJSON, check the geometry, measure it."""

import json
from dataclasses import dataclass
from pathlib import Path

import ee
from pyproj import Geod
from shapely.geometry import shape
from shapely.validation import explain_validity

POLYGON_TYPES = ("Polygon", "MultiPolygon")
WGS84 = Geod(ellps="WGS84")


class AreaError(ValueError):
    """A geometry that cannot be used as an area."""


@dataclass(frozen=True)
class Area:
    name: str
    geometry: dict  # GeoJSON Polygon or MultiPolygon, longitude/latitude
    area_km2: float

    def to_ee(self) -> ee.Geometry:
        return ee.Geometry(self.geometry)


def make_area(geometry: dict, name: str) -> Area:
    """Check a GeoJSON geometry and turn it into an Area."""
    kind = geometry.get("type") if isinstance(geometry, dict) else None
    if kind not in POLYGON_TYPES:
        raise AreaError(f"{name}: expected a Polygon or MultiPolygon, got {kind}")

    try:
        polygon = shape(geometry)
    except (ValueError, TypeError, IndexError, AttributeError) as error:
        raise AreaError(f"{name}: unreadable coordinates ({error})") from None

    west, south, east, north = polygon.bounds
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise AreaError(f"{name}: coordinates must be longitude, latitude in degrees")

    if not polygon.is_valid:
        raise AreaError(f"{name}: invalid polygon ({explain_validity(polygon)})")

    if polygon.is_empty or polygon.area == 0:
        raise AreaError(f"{name}: the polygon has no area")

    area_m2, _ = WGS84.geometry_area_perimeter(polygon)
    return Area(name=name, geometry=geometry, area_km2=abs(area_m2) / 1e6)


def load_areas(source: dict | str | Path) -> list[Area]:
    """Areas from a GeoJSON FeatureCollection, Feature or geometry (dict or file).

    Each area is named after its "name" property, or "Area 1", "Area 2", ...
    """
    data = json.loads(Path(source).read_text()) if isinstance(source, str | Path) else source

    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    else:
        features = [{"geometry": data}]

    if not features:
        raise AreaError("the file contains no areas")

    areas = []
    for number, feature in enumerate(features, start=1):
        name = (feature.get("properties") or {}).get("name") or f"Area {number}"
        areas.append(make_area(feature.get("geometry"), name))

    names = [area.name for area in areas]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise AreaError(f"area names must be unique: {', '.join(duplicates)}")
    return areas
