"""The variables Magonia can extract, and everything known about each one."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Learn:
    """What a researcher needs to know to use a variable well, in plain words."""

    what: str
    formula: str
    reading: str  # how to read the values
    uses: tuple[str, ...]
    limits: tuple[str, ...]


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
    pixel_m: int  # pixel size used when averaging over an area
    cadence: str
    quality: str
    licence: str
    citation: str
    scales: tuple[int, ...] = ()  # common accumulation periods in months, for SPEI
    sampling: str = "mean"  # "mean" over the area, or the "centre" cell for coarse grids
    group: str = ""
    learn: Learn | None = None
    large: bool = False  # values of order one or more, written with fewer decimals

    def to_dict(self) -> dict:
        return asdict(self)


MODIS_LICENCE = "NASA LP DAAC: no restrictions on use or redistribution"
MODIS_QA = "Pixels with SummaryQA of 2 (snow or ice) or 3 (cloudy) are removed."
DIDAN = (
    "Didan, K. (2021). MOD13Q1 MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid "
    "V061. NASA EOSDIS Land Processes DAAC."
)
ERA5 = {
    "product": "ERA5-Land monthly",
    "collection": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
    "resolution": "0.1°",
    "pixel_m": 11132,  # 0.1° of latitude
    "cadence": "monthly",
    "quality": "A reanalysis, weather observations merged with a weather model; no quality flags.",
    "licence": "Copernicus licence: free use, with acknowledgement of Copernicus",
    "citation": "Muñoz-Sabater, J. et al. (2021). ERA5-Land: a state-of-the-art global "
    "reanalysis dataset for land applications. Earth System Science Data 13, 4349-4383.",
    "sampling": "centre",
}
MODIS_500M = (
    "A model estimate, uncertain where land covers mix.",
    "500 m pixels are much larger than most fields.",
    "Saturates in dense canopies.",
)
MIXED = "At 250 m a pixel mixes trees, soil and neighbouring fields."
LAST_COMPOSITE = (
    "Each value is an 8-day total shown per day; the last composite of a year covers 5 or 6 "
    "days, so it reads slightly low."
)

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
    pixel_m=250,
    cadence="16 days",
    quality=MODIS_QA,
    licence=MODIS_LICENCE,
    citation=DIDAN,
    group="Vegetation greenness",
    learn=Learn(
        what="How green and dense the vegetation is. Leaves absorb red light for "
        "photosynthesis and reflect near-infrared strongly, so the more healthy leaves, the "
        "wider the gap between the two.",
        formula="NDVI = (NIR − red) / (NIR + red)",
        reading="From −1 to 1. Water, snow and bare soil sit near 0 or below, sparse "
        "vegetation around 0.2 to 0.4, dense crops and forests 0.6 to 0.9.",
        uses=(
            "Following growing seasons and how a crop develops",
            "Spotting drought or damage as a drop against the usual year",
            "Comparing land covers, such as olive orchards and forest",
            "The usual target when forecasting vegetation",
        ),
        limits=(
            (
                "Saturates over dense vegetation: above about 0.8, more leaves barely change "
                "it (EVI keeps responding)."
            ),
            "Raised by bright soil between sparse trees (SAVI corrects for this).",
            MIXED,
        ),
    ),
)

# Soil-adjusted vegetation index (Huete 1988): like NDVI, but less raised by bright bare soil
# between trees, which matters in sparse orchards. Computed from the same product's red and
# near-infrared reflectances, with the same quality flags.
SAVI = Variable(
    key="savi",
    name="SAVI",
    units="",
    product="MODIS Terra MOD13Q1 v6.1",
    collection="MODIS/061/MOD13Q1",
    band="SAVI",  # computed: 1.5 (NIR - red) / (NIR + red + 0.5), reflectances scaled by 0.0001
    scale=1.0,
    offset=0.0,
    resolution="250 m",
    pixel_m=250,
    cadence="16 days",
    quality=MODIS_QA,
    licence=MODIS_LICENCE,
    citation="Huete, A.R. (1988). A soil-adjusted vegetation index (SAVI). Remote Sensing of "
    "Environment 25, 295-309. Bands from Didan, K. (2021), MOD13Q1 V061.",
    group="Vegetation greenness",
    learn=Learn(
        what="NDVI corrected for the soil showing between plants. Bright soil between sparse "
        "trees pushes NDVI around; SAVI adds a constant, L = 0.5, that damps the effect.",
        formula="SAVI = 1.5 (NIR − red) / (NIR + red + 0.5)",
        reading="On the same scale as NDVI but lower: about 0.1 to 0.3 for sparse orchards, "
        "up to 0.6 to 0.8 for dense vegetation.",
        uses=(
            "Sparse canopies: olive orchards, vineyards, rangeland, crops early in the season",
            "Arid and semi-arid regions, where soil fills much of each pixel",
        ),
        limits=(
            "L = 0.5 is a compromise; very sparse or very dense cover would want another value.",
            "Still saturates over dense vegetation.",
            MIXED,
        ),
    ),
)

EVI = Variable(
    key="evi",
    name="EVI",
    units="",
    product="MODIS Terra MOD13Q1 v6.1",
    collection="MODIS/061/MOD13Q1",
    band="EVI",
    scale=0.0001,
    offset=0.0,
    resolution="250 m",
    pixel_m=250,
    cadence="16 days",
    quality=MODIS_QA,
    licence=MODIS_LICENCE,
    citation="Huete, A., Didan, K., Miura, T., Rodriguez, E.P., Gao, X., Ferreira, L.G. (2002). "
    "Overview of the radiometric and biophysical performance of the MODIS vegetation indices. "
    "Remote Sensing of Environment 83, 195-213. Data from " + DIDAN,
    group="Vegetation greenness",
    learn=Learn(
        what="An enhanced greenness index. It uses the blue band to correct for haze and a "
        "soil term, and keeps responding in dense, leafy vegetation where NDVI has flattened.",
        formula="EVI = 2.5 (NIR − red) / (NIR + 6 red − 7.5 blue + 1)",
        reading="Usually 0 to about 0.8: sparse vegetation 0.1 to 0.2, dense forest and crops "
        "at their peak 0.4 to 0.7.",
        uses=(
            "Forests and dense crops, where NDVI saturates",
            "Productivity: it follows photosynthesis closely",
            "Regions with haze or smoke",
        ),
        limits=(
            "Noisier than NDVI over sparse vegetation and bright surfaces.",
            "Sensitive to the sun and viewing angles on slopes.",
            MIXED,
        ),
    ),
)

LAI = Variable(
    key="lai",
    name="Leaf area index",
    units="m²/m²",
    product="MODIS Terra MOD15A2H v6.1",
    collection="MODIS/061/MOD15A2H",
    band="Lai_500m",
    scale=0.1,
    offset=0.0,
    resolution="500 m",
    pixel_m=500,
    cadence="8 days",
    quality="Pixels from the backup algorithm or not retrieved (FparLai_QC) are removed; "
    "values marking water, cities or barren land are always removed.",
    licence=MODIS_LICENCE,
    citation="Myneni, R., Knyazikhin, Y., Park, T. (2021). MOD15A2H MODIS/Terra Leaf Area "
    "Index/FPAR 8-Day L4 Global 500m SIN Grid V061. NASA EOSDIS Land Processes DAAC.",
    group="Canopy",
    learn=Learn(
        what="The area of leaves above each square metre of ground, counting one side. A value "
        "of 3 means three layers of leaves.",
        formula="Estimated by a radiative-transfer model from MODIS reflectances and the "
        "land-cover type, not computed by a simple formula.",
        reading="0 for bare ground, about 0.5 to 2 for sparse orchards and grassland, 3 to 6 "
        "for crops at their peak and dense forests.",
        uses=(
            "Crop growth and yield models, which need leaf area",
            "Water and carbon exchange: leaves are where both happen",
            "Comparing how the canopy develops from year to year",
        ),
        limits=MODIS_500M,
    ),
)

FPAR = Variable(
    key="fpar",
    name="FPAR",
    units="",
    product="MODIS Terra MOD15A2H v6.1",
    collection="MODIS/061/MOD15A2H",
    band="Fpar_500m",
    scale=0.01,
    offset=0.0,
    resolution="500 m",
    pixel_m=500,
    cadence="8 days",
    quality=LAI.quality,
    licence=MODIS_LICENCE,
    citation=LAI.citation,
    group="Canopy",
    learn=Learn(
        what="The fraction of the sunlight plants can use for photosynthesis (400 to 700 nm) "
        "that the canopy absorbs. It links the canopy to how much the plants can grow.",
        formula="Estimated with LAI by the same model; GPP models then use "
        "GPP = efficiency × FPAR × incoming light.",
        reading="From 0 to 1: about 0.1 to 0.3 for sparse cover, above 0.8 for dense, green "
        "canopies.",
        uses=(
            "Productivity models based on light-use efficiency",
            "Crop monitoring, alongside LAI",
        ),
        limits=MODIS_500M,
    ),
)

GPP = Variable(
    key="gpp",
    name="Gross primary production",
    units="g C/m²/day",
    product="MODIS Terra MOD17A2HGF v6.1 (gap-filled)",
    collection="MODIS/061/MOD17A2HGF",
    band="Gpp",
    scale=0.1 / 8,  # kg C/m² per 8 days, scaled by 0.0001, as g C/m² per day
    offset=0.0,
    resolution="500 m",
    pixel_m=500,
    cadence="8 days",
    quality="The gap-filled version, made once a year; values marking water, cities or "
    "barren land are removed.",
    licence=MODIS_LICENCE,
    citation="Running, S., Zhao, M. (2021). MOD17A2HGF MODIS/Terra Gross Primary Productivity "
    "Gap-Filled 8-Day L4 Global 500 m SIN Grid V061. NASA EOSDIS Land Processes DAAC.",
    group="Productivity",
    large=True,
    learn=Learn(
        what="The carbon the vegetation takes up by photosynthesis. MODIS estimates it from "
        "FPAR, sunlight and the weather, reduced when it is too cold or the air too dry.",
        formula="GPP = ε × FPAR × PAR, with the efficiency ε lowered by low temperature and "
        "high vapour-pressure deficit",
        reading="Near 0 when vegetation is dormant or dry; a few g C/m² per day for crops "
        "and forests in their growing season.",
        uses=(
            "Carbon uptake and productivity of crops and forests",
            "How drought slows growth",
            "Comparing the productivity of land covers",
        ),
        limits=(
            "A model driven by coarse weather data, not a measurement.",
            "It relies on a land-cover map that may misclassify small orchards.",
            LAST_COMPOSITE,
            "The gap-filled version ends with the last complete year.",
        ),
    ),
)

ET = Variable(
    key="et",
    name="Evapotranspiration",
    units="mm/day",
    product="MODIS Terra MOD16A2GF v6.1 (gap-filled)",
    collection="MODIS/061/MOD16A2GF",
    band="ET",
    scale=0.1 / 8,  # kg/m² (mm) per 8 days, scaled by 0.1, as mm per day
    offset=0.0,
    resolution="500 m",
    pixel_m=500,
    cadence="8 days",
    quality=GPP.quality,
    licence=MODIS_LICENCE,
    citation="Running, S., Mu, Q., Zhao, M., Moreno, A. (2021). MOD16A2GF MODIS/Terra Net "
    "Evapotranspiration Gap-Filled 8-Day L4 Global 500 m SIN Grid V061. NASA EOSDIS Land "
    "Processes DAAC.",
    group="Water",
    large=True,
    learn=Learn(
        what="The water leaving the land: evaporation from the soil and transpiration through "
        "leaves. MODIS estimates it from energy and weather with the Penman–Monteith equation.",
        formula="Penman–Monteith, driven by MODIS LAI, FPAR and albedo and by daily weather",
        reading="0 to 1 mm per day in dry seasons or for dormant vegetation; 2 to 6 mm per day "
        "for well-watered crops in summer.",
        uses=(
            "Water use of crops and orchards, and irrigation",
            "The water balance, with rainfall",
            "Drought: it falls when plants close their stomata",
        ),
        limits=(
            "A model with coarse weather inputs, not a measurement.",
            "Unreliable for small irrigated fields at 500 m.",
            LAST_COMPOSITE,
            "The gap-filled version ends with the last complete year.",
        ),
    ),
)

# Normalised difference moisture index (Gao 1996): water in leaves, from near- and shortwave
# infrared. MOD13Q1 has no 1.6 µm band, so it comes from the 8-day surface reflectance.
NDMI = Variable(
    key="ndmi",
    name="NDMI",
    units="",
    product="MODIS Terra MOD09A1 v6.1",
    collection="MODIS/061/MOD09A1",
    band="NDMI",  # computed: (NIR - SWIR1) / (NIR + SWIR1), bands 2 and 6
    scale=1.0,
    offset=0.0,
    resolution="500 m",
    pixel_m=500,
    cadence="8 days",
    quality="Pixels whose StateQA reports cloud, mixed cloud or cloud shadow are removed.",
    licence=MODIS_LICENCE,
    citation="Gao, B.-C. (1996). NDWI, a normalized difference water index for remote sensing "
    "of vegetation liquid water from space. Remote Sensing of Environment 58, 257-266. Bands "
    "from Vermote, E. (2021), MOD09A1 MODIS/Terra Surface Reflectance 8-Day L3 Global 500m "
    "SIN Grid V061.",
    group="Water",
    learn=Learn(
        what="How much water the leaves hold. Water in leaves absorbs shortwave infrared, so "
        "drier leaves reflect more of it.",
        formula="NDMI = (NIR − SWIR) / (NIR + SWIR), with SWIR at 1.6 µm (MODIS band 6)",
        reading="From −1 to 1; higher means wetter leaves. Values below 0 are typical of dry "
        "vegetation or bare soil.",
        uses=(
            "Water stress in crops and orchards, often before greenness drops",
            "Following irrigation",
            "Fire risk from drying vegetation",
        ),
        limits=(
            "500 m pixels, coarser than NDVI.",
            "Where the canopy is sparse, it also responds to wet soil.",
            (
                "Also called NDWI (Gao), a name used too for an index of open water, a "
                "different thing."
            ),
        ),
    ),
)

NBR = Variable(
    key="nbr",
    name="NBR",
    units="",
    product="MODIS Terra MOD13Q1 v6.1",
    collection="MODIS/061/MOD13Q1",
    band="NBR",  # computed: (NIR - SWIR2) / (NIR + SWIR2), reflectances scaled by 0.0001
    scale=1.0,
    offset=0.0,
    resolution="250 m",
    pixel_m=250,
    cadence="16 days",
    quality=MODIS_QA,
    licence=MODIS_LICENCE,
    citation="Key, C.H., Benson, N.C. (2006). Landscape assessment: the Normalized Burn Ratio. "
    "USDA Forest Service RMRS-GTR-164-CD. Bands from " + DIDAN,
    group="Fire and disturbance",
    learn=Learn(
        what="Separates healthy vegetation from burned ground. Fire lowers near-infrared and "
        "raises shortwave infrared, so NBR falls sharply after a fire.",
        formula="NBR = (NIR − SWIR) / (NIR + SWIR), with SWIR at 2.1 µm (MODIS band 7)",
        reading="High for healthy vegetation, near or below 0 for burned or bare ground. The "
        "drop from before to after a fire, dNBR, measures how severe it was.",
        uses=(
            "Burned areas and fire severity",
            "How vegetation recovers after a fire",
            "Other disturbances, such as clearing or storm damage",
        ),
        limits=(
            "250 m is coarse for small fires.",
            "Seasonal drying lowers it too: compare with the same season of other years.",
        ),
    ),
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
    pixel_m=1000,
    cadence="8 days",
    quality="Pixels whose QC_Day reports an LST error above 2 K are removed.",
    licence=MODIS_LICENCE,
    citation="Wan, Z., Hook, S., Hulley, G. (2021). MOD11A2 MODIS/Terra Land Surface "
    "Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061. NASA EOSDIS Land Processes DAAC.",
    group="Climate",
    large=True,
    learn=Learn(
        what="How hot the ground surface is, from the heat it radiates, seen at about 10:30 "
        "in the morning. It is not the air temperature: a dry surface in summer can be much "
        "hotter than the air.",
        formula="From thermal infrared (11 and 12 µm), corrected for emissivity and the atmosphere",
        reading="In °C. Dense, well-watered vegetation stays cooler than bare or dry ground.",
        uses=(
            "Heat and water stress: a plant that cannot transpire warms up",
            "Drought indices that combine it with NDVI",
            "Comparing how land covers heat up",
        ),
        limits=(
            "Clouds hide the surface, so cloudy dates are missing.",
            "1 km pixels are often larger than the study area.",
            "Daytime only, at the time the satellite passes.",
        ),
    ),
)

AIR_TEMPERATURE = Variable(
    key="air_temperature",
    name="Air temperature",
    units="°C",
    band="temperature_2m",
    scale=1.0,
    offset=-273.15,
    group="Climate",
    large=True,
    learn=Learn(
        what="The month's mean air temperature 2 m above the ground, from ERA5-Land.",
        formula="Mean of hourly values, day and night",
        reading="In °C, averaged over day and night, so lower than daytime peaks.",
        uses=(
            "Heat and frost limits on growth",
            "Separating the effect of heat from that of drought",
            "Next to LST, which is the ground surface, not the air",
        ),
        limits=(
            "A grid of about 9 to 11 km: valleys and slopes are averaged together.",
            "A monthly mean hides heat waves.",
        ),
    ),
    **ERA5,
)

RAIN = Variable(
    key="rain",
    name="Rainfall",
    units="mm",
    band="total_precipitation_sum",
    scale=1000.0,  # metres of water in the month, as millimetres
    offset=0.0,
    group="Climate",
    large=True,
    learn=Learn(
        what="Total rain and snow in the month, from ERA5-Land, which merges weather "
        "observations with a weather model.",
        formula="Sum over the month of the model's hourly precipitation",
        reading="Millimetres in the month.",
        uses=(
            "The water supply of vegetation: compare with NDVI a month or a few later",
            "The water balance, with evapotranspiration",
            "Understanding drought month by month",
        ),
        limits=(
            "A grid of about 9 to 11 km smooths out local storms.",
            "Less accurate where few weather stations report.",
            "Rain only: irrigation is not included.",
        ),
    ),
    **ERA5,
)

SOIL_MOISTURE = Variable(
    key="soil_moisture",
    name="Soil moisture",
    units="m³/m³",
    band="volumetric_soil_water_layer_1",
    scale=1.0,
    offset=0.0,
    group="Water",
    learn=Learn(
        what="The share of the top 7 cm of soil that is water, from ERA5-Land.",
        formula="Volume of water ÷ volume of soil, from the model's water balance",
        reading="From 0, dry, to about 0.5, saturated; most soils sit between 0.1 and 0.4, "
        "depending on texture.",
        uses=(
            "Water available to crops, between the rain and the plants' response",
            "Drought, month by month",
            "Explaining the delay between rainfall and NDVI",
        ),
        limits=(
            "The top layer only; tree roots draw from much deeper.",
            "A model estimate on a grid of about 9 to 11 km, not a measurement.",
            "Irrigation is not included.",
        ),
    ),
    **ERA5,
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
    pixel_m=55660,  # 0.5° of latitude
    cadence="monthly",
    quality="No quality flags; the grid cell is far larger than most fields.",
    licence="Open Database License (ODbL) 1.0",
    citation="Beguería, S., Vicente-Serrano, S.M., Reig, F., Latorre, B. (2014). "
    "Standardized precipitation evapotranspiration index (SPEI) revisited. "
    "International Journal of Climatology 34, 3001-3023.",
    scales=(1, 3, 6, 12, 24, 48),
    sampling="centre",
    group="Drought",
    learn=Learn(
        what="How wet or dry a period was compared with what is usual in that place: rainfall "
        "minus the water the air demands, added up over 1 to 48 months and standardised.",
        formula="Precipitation − potential evapotranspiration, summed over the time scale and "
        "fitted to a log-logistic distribution",
        reading="0 is normal. −1 to −1.5 is moderate drought, −1.5 to −2 severe, below −2 "
        "extreme; positive values are wetter than usual.",
        uses=(
            "When droughts happened and how severe they were",
            "How long vegetation takes to respond: short scales for crops, longer for trees",
            "Comparing drought across regions, since it is standardised",
        ),
        limits=(
            "A 0.5° grid (about 55 km): one value for a whole region.",
            "Climate only: it knows nothing of irrigation.",
            "Depends on the reference period used to standardise it.",
        ),
    ),
)

CATALOGUE = {
    variable.key: variable
    for variable in (
        NDVI,
        SAVI,
        EVI,
        LAI,
        FPAR,
        GPP,
        NDMI,
        ET,
        SOIL_MOISTURE,
        NBR,
        LST,
        AIR_TEMPERATURE,
        RAIN,
        SPEI,
    )
}

# What season dates can be computed from: measures of the vegetation itself
SEASONAL = {"ndvi", "savi", "evi", "lai", "fpar", "gpp"}


def large(key: str) -> bool:
    """Values of order one or more, such as temperatures, written with fewer decimals."""
    variable = CATALOGUE.get(key)
    return variable.large if variable else False


# Days between two values, for methods that depend on the time step
CADENCE_DAYS = {"16 days": 16.0, "8 days": 8.0, "monthly": 365.25 / 12}


def get_variable(key: str) -> Variable:
    """The catalogue entry for a variable key such as "ndvi"."""
    try:
        return CATALOGUE[key]
    except KeyError:
        known = ", ".join(CATALOGUE)
        raise KeyError(f"unknown variable {key!r}; choose one of {known}") from None
