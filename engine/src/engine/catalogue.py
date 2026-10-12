"""The variables Magonia can extract, and everything known about each one."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Variable:
    key: str
    name: str
    units: str
    product: str
    collection: str  # Earth Engine collection ID
    band: str  # "{scale:02d}" is replaced by the time scale for multi-scale indices
    scale: float  # stored value * scale + offset = value in units
    offset: float
    resolution: str
    cadence: str
    quality: str
    licence: str
    citation: str
    scales: tuple[int, ...] = ()  # accumulation periods in months, for SPEI

    def to_dict(self) -> dict:
        return asdict(self)


NDVI = Variable(
    key="ndvi",
    name="NDVI",
    units="",
    product="MODIS Terra MOD13Q1 v6.1",
    collection="MODIS/061/MOD13Q1",
    band="NDVI",
    scale=0.0001,
    offset=0.0,
    resolution="250 m",
    cadence="16 days",
    quality="Pixels with SummaryQA of 2 (snow or ice) or 3 (cloudy) are removed.",
    licence="NASA LP DAAC: no restrictions on use or redistribution",
    citation="Didan, K. (2021). MOD13Q1 MODIS/Terra Vegetation Indices 16-Day L3 Global "
    "250m SIN Grid V061. NASA EOSDIS Land Processes DAAC.",
)

LST = Variable(
    key="lst",
    name="Land surface temperature (day)",
    units="°C",
    product="MODIS Terra MOD11A2 v6.1",
    collection="MODIS/061/MOD11A2",
    band="LST_Day_1km",
    scale=0.02,
    offset=-273.15,
    resolution="1 km",
    cadence="8 days",
    quality="Pixels whose QC_Day reports an LST error above 2 K are removed.",
    licence="NASA LP DAAC: no restrictions on use or redistribution",
    citation="Wan, Z., Hook, S., Hulley, G. (2021). MOD11A2 MODIS/Terra Land Surface "
    "Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061. NASA EOSDIS Land Processes DAAC.",
)

SPEI = Variable(
    key="spei",
    name="SPEI",
    units="",
    product="SPEIbase v2.11",
    collection="CSIC/SPEI/2_11",
    band="SPEI_{scale:02d}_month",
    scale=1.0,
    offset=0.0,
    resolution="0.5°",
    cadence="monthly",
    quality="No quality flags; the grid cell is far larger than most fields.",
    licence="Open Database License (ODbL) 1.0",
    citation="Beguería, S., Vicente-Serrano, S.M., Reig, F., Latorre, B. (2014). "
    "Standardized precipitation evapotranspiration index (SPEI) revisited. "
    "International Journal of Climatology 34, 3001-3023.",
    scales=(1, 3, 6, 12, 24, 48),
)

CATALOGUE = {variable.key: variable for variable in (NDVI, LST, SPEI)}


def get_variable(key: str) -> Variable:
    """The catalogue entry for a variable key such as "ndvi"."""
    try:
        return CATALOGUE[key]
    except KeyError:
        known = ", ".join(CATALOGUE)
        raise KeyError(f"unknown variable {key!r}; choose one of {known}") from None
