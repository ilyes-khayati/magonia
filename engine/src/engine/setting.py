"""Where a study was made, read by code from its title and abstract, and whether that is the
researcher's setting.

A paper can support a sentence and still say nothing about the researcher's area. Asked why
NDVI is lowest in July in a Tunisian orchard, Magon cited a paper whose NDVI was lowest in
February, and explained the delay between drought and greenness with monsoon crops in central
India: each sentence was faithful to its paper, so the support check passed it (explanation
test, 15 Nov). A finding carries over to another setting only when what moderates it is the
same there. External validity has four dimensions: the units studied, the treatment, the
outcome and the context (Egami and Hartman, 2023). For a paper that explains vegetation these
are the vegetation, the driver, the variable measured, and the place and its climate.

Code reads from the abstract the three it can read reliably: the place (a country or region),
the climate when it is named, and the vegetation. The researcher's place comes from where
their areas lie, and their vegetation from the names they gave them. A dimension that cannot
be read on either side is not compared. A paper differs when one dimension read on both sides
does not match. Its setting is then given to the model with the paper, and named by code in
any sentence that uses it without saying where it comes from. The direction of an effect is
what carries over most safely to another setting (Egami and Hartman, 2023); its size and
timing are what the setting changes.
"""

import re
from dataclasses import dataclass, field

# Places, by region. A country, or a region within one, as abstracts name them
REGIONS: dict[str, tuple[str, ...]] = {
    "the Mediterranean": (
        "Tunisia",
        # Tunisia's governorates, where Magonia's first studies are (a paper set in Kairouan
        # is a Mediterranean study; "Jendouba (2019)" is a place and a year, not a reference)
        "Ariana",
        "Ben Arous",
        "Manouba",
        "Nabeul",
        "Zaghouan",
        "Bizerte",
        "Béja",
        "Beja",
        "Jendouba",
        "Le Kef",
        "Siliana",
        "Sousse",
        "Monastir",
        "Mahdia",
        "Sfax",
        "Kairouan",
        "Kasserine",
        "Sidi Bouzid",
        "Gabès",
        "Gabes",
        "Medenine",
        "Médenine",
        "Tataouine",
        "Gafsa",
        "Tozeur",
        "Kebili",
        "Kébili",
        "Algeria",
        "Morocco",
        "Libya",
        "Spain",
        "Portugal",
        "Italy",
        "Greece",
        "Cyprus",
        "Malta",
        "Croatia",
        "Albania",
        "Lebanon",
        "Israel",
        "Palestine",
        "Syria",
        "Turkey",
        "Türkiye",
        "Maghreb",
        "North Africa",
        "Iberian Peninsula",
        "Iberia",
        "Andalusia",
        "Sicily",
        "Sardinia",
        "Crete",
        "Apulia",
        "Puglia",
        "Catalonia",
        "Jordan",
    ),
    "South Asia": (
        "India",
        "Pakistan",
        "Bangladesh",
        "Nepal",
        "Sri Lanka",
        "Indo-Gangetic",
        "Punjab",
        "Maharashtra",
        "Rajasthan",
        "Karnataka",
        "Tamil Nadu",
        "Gujarat",
        "Bihar",
    ),
    "East Asia": (
        "China",
        "Mongolia",
        "Korea",
        "Japan",
        "Loess Plateau",
        "Tibetan Plateau",
        "Qinghai",
        "Yellow River",
        "Yangtze",
        "Xinjiang",
        "Inner Mongolia",
    ),
    "Southeast Asia": (
        "Vietnam",
        "Thailand",
        "Indonesia",
        "Malaysia",
        "Philippines",
        "Cambodia",
        "Myanmar",
        "Laos",
    ),
    "sub-Saharan Africa": (
        "Ethiopia",
        "Kenya",
        "Tanzania",
        "Nigeria",
        "Niger",
        "Mali",
        "Burkina Faso",
        "Senegal",
        "Sudan",
        "Somalia",
        "South Africa",
        "Zimbabwe",
        "Zambia",
        "Mozambique",
        "Ghana",
        "Sahel",
        "East Africa",
        "West Africa",
        "Horn of Africa",
        "Botswana",
        "Namibia",
        "Malawi",
        "Uganda",
    ),
    "the Middle East": ("Iran", "Iraq", "Saudi Arabia", "Yemen", "Oman", "Kuwait", "Qatar"),
    "Central Asia": (
        "Kazakhstan",
        "Uzbekistan",
        "Turkmenistan",
        "Kyrgyzstan",
        "Tajikistan",
        "Afghanistan",
    ),
    "North America": (
        "United States",
        "USA",
        "U.S.",
        "Canada",
        "Mexico",
        "California",
        "Alaska",
        "Texas",
        "Great Plains",
        "Midwest",
        "Nebraska",
        "Kansas",
        "Iowa",
    ),
    "South America": (
        "Brazil",
        "Argentina",
        "Chile",
        "Peru",
        "Colombia",
        "Bolivia",
        "Uruguay",
        "Paraguay",
        "Amazon",
        "Pampas",
        "Cerrado",
    ),
    "temperate Europe": (
        "Germany",
        "France",
        "United Kingdom",
        "England",
        "Netherlands",
        "Belgium",
        "Poland",
        "Czech",
        "Hungary",
        "Romania",
        "Austria",
        "Switzerland",
        "Denmark",
        "Sweden",
        "Finland",
        "Norway",
        "Ireland",
        "Ukraine",
        "Russia",
    ),
    "Australia": ("Australia", "New Zealand"),
}
PLACE_REGION = {place: region for region, places in REGIONS.items() for place in places}
PLACE = re.compile(
    r"(?<![\w-])("
    + "|".join(re.escape(p) for p in sorted(PLACE_REGION, key=len, reverse=True))
    + r")(?![\w-])"
)
# Indian, Chinese, Brazilian…: a place named by its adjective
ADJECTIVES = {
    "Tunisian": "Tunisia",
    "Algerian": "Algeria",
    "Moroccan": "Morocco",
    "Spanish": "Spain",
    "Portuguese": "Portugal",
    "Italian": "Italy",
    "Greek": "Greece",
    "Turkish": "Turkey",
    "Indian": "India",
    "Pakistani": "Pakistan",
    "Chinese": "China",
    "Mongolian": "Mongolia",
    "Ethiopian": "Ethiopia",
    "Kenyan": "Kenya",
    "Nigerian": "Nigeria",
    "Iranian": "Iran",
    "Brazilian": "Brazil",
    "Argentinian": "Argentina",
    "Australian": "Australia",
    "German": "Germany",
    "French": "France",
    "Mexican": "Mexico",
    "Canadian": "Canada",
    "American": "United States",
    "Sahelian": "Sahel",
    "Iberian": "Iberia",
}
ADJECTIVE = re.compile(r"\b(" + "|".join(ADJECTIVES) + r")\b(?!\s+(Ocean|Sea|Plate)\b)")
# a study of the whole globe, or of a continent, is about no one setting
# a study of the whole world, not "global warming" or a "continental climate" (review of 18 Nov)
GLOBAL = re.compile(
    r"\b(global(ly)?|worldwide|world-wide|across the globe|continental)\b"
    r"(?!\s+(warming|change|climate|climates|scale models?|circulation))",
    re.IGNORECASE,
)

# Climates an abstract names, by the region whose climate it is
CLIMATES: dict[str, str] = {
    r"monsoon\w*": "monsoon",
    r"\btropic(al|s)\b": "tropical",  # not "subtropical", a different climate
    r"boreal|sub-?arctic|tundra|permafrost": "boreal",
    r"mediterranean[- ]climate|mediterranean[- ]type": "Mediterranean",
}
# which climates are a region's own, so that one named elsewhere is a difference
CLIMATE_OF = {"the Mediterranean": {"Mediterranean"}}

# The vegetation a study was made on, by kind; one word can name several
COVERS: dict[str, str] = {
    r"olives?|olive (groves?|orchards?|trees?)|olea\b": "olive",
    r"orchards?|fruit trees?|citrus|almonds?|vineyards?|grapevines?|tree crops?": "tree crops",
    r"wheat|barley|cereals?|grain crops?": "cereals",
    r"maize|corn\b": "maize",
    r"\brice\b|paddy|paddies": "rice",
    r"soybeans?|cotton|sugarcane|groundnut|peanuts?|sorghum|millet": "field crops",
    # not "random forest" or "isolation forest", which are models
    r"(?<!random )(?<!isolation )forests?|woodlands?|\bpines?\b|\boaks?\b|conifer\w*": "forest",
    r"grasslands?|pastures?|rangelands?|steppes?|meadows?|savannas?|savannahs?": "grassland",
    r"shrublands?|maquis|garrigue|scrub\w*": "shrubland",
}
# the kinds that can stand for the researcher's vegetation when they name it
ALIKE = {
    "olive": {"olive", "tree crops"},
    "tree crops": {"olive", "tree crops"},
    "cereals": {"cereals"},
    "maize": {"maize", "field crops"},
    "rice": {"rice"},
    "field crops": {"field crops", "maize"},
    "forest": {"forest"},
    "grassland": {"grassland"},
    "shrubland": {"shrubland"},
}

# Where the areas lie, as the platform tells Magon
WHERE = re.compile(r"areas lie near (-?\d+(?:\.\d+)?)° ([NS]), (-?\d+(?:\.\d+)?)° ([EW])")
# Boxes around the regions an area can lie in: (south, north, west, east), in degrees
BOXES: dict[str, tuple[float, float, float, float]] = {
    "Tunisia": (30.2, 37.6, 7.5, 11.6),
}
REGION_BOXES: dict[str, tuple[float, float, float, float]] = {
    "the Mediterranean": (30.0, 46.0, -10.0, 37.0),
    "South Asia": (5.0, 37.0, 60.0, 97.0),
    "East Asia": (18.0, 54.0, 97.0, 146.0),
    "sub-Saharan Africa": (-35.0, 18.0, -18.0, 52.0),
    "North America": (15.0, 72.0, -170.0, -50.0),
    "South America": (-56.0, 13.0, -82.0, -34.0),
    "temperate Europe": (46.0, 72.0, -11.0, 40.0),
    "Australia": (-48.0, -10.0, 112.0, 179.0),
}


@dataclass
class Setting:
    """Where a study, or the researcher's work, was made: what code could read of it."""

    places: list[str] = field(default_factory=list)  # most named first
    regions: set[str] = field(default_factory=set)
    climates: set[str] = field(default_factory=set)
    covers: list[str] = field(default_factory=list)  # most named first
    worldwide: bool = False

    @property
    def known(self) -> bool:
        return bool(self.places or self.regions or self.covers or self.climates)

    def describe(self) -> str:
        """In a few words, e.g. "India, on rice" or "the Mediterranean, on olive"."""
        where = self.places[0] if self.places else next(iter(sorted(self.regions)), "")
        if self.climates and not where:
            where = f"a {min(self.climates)} climate"
        what = self.covers[0] if self.covers else ""
        if where and what:
            return f"{where}, on {what}"
        return where or (f"on {what}" if what else "")


def counted(found: list[str]) -> list[str]:
    """Distinct values, the most frequent first, ties in order of appearance."""
    order = list(dict.fromkeys(found))
    return sorted(order, key=lambda v: -found.count(v))


def read(text: str) -> Setting:
    """The setting a title and abstract state."""
    places = [m.group(1) for m in PLACE.finditer(text)]
    places += [ADJECTIVES[m.group(1)] for m in ADJECTIVE.finditer(text)]
    # "Mediterranean" alone names the region, and its climate
    mediterranean = re.search(r"\bMediterranean\b", text) is not None
    climates = {
        name for pattern, name in CLIMATES.items() if re.search(pattern, text, re.IGNORECASE)
    }
    if mediterranean:
        climates.add("Mediterranean")
    covers = []
    for pattern, kind in COVERS.items():
        covers += [kind] * len(re.findall(rf"\b(?:{pattern})", text, re.IGNORECASE))
    regions = {PLACE_REGION[p] for p in places}
    if mediterranean:
        regions.add("the Mediterranean")
    return Setting(
        places=counted(places),
        regions=regions,
        climates=climates,
        covers=counted(covers),
        worldwide=bool(GLOBAL.search(text)),
    )


def of_paper(paper) -> Setting:
    """The setting of a paper, from its title and abstract."""
    return read(f"{paper.title or ''}. {paper.abstract or ''}")


def located(lat: float, lon: float) -> tuple[list[str], set[str]]:
    """The places and regions whose boxes hold a point."""
    inside = [name for name, (s, n, w, e) in BOXES.items() if s <= lat <= n and w <= lon <= e]
    regions = {
        name for name, (s, n, w, e) in REGION_BOXES.items() if s <= lat <= n and w <= lon <= e
    }
    return inside, regions


def of_workspace(context: list[str], areas: list[str]) -> Setting:
    """The researcher's setting: where their areas lie, and the vegetation their names give."""
    places: list[str] = []
    regions: set[str] = set()
    for line in context:
        if m := WHERE.search(line):
            lat = float(m.group(1)) * (1 if m.group(2) == "N" else -1)
            lon = float(m.group(3)) * (1 if m.group(4) == "E" else -1)
            places, regions = located(lat, lon)
    named = read(" ".join(areas + [c for c in context if c.startswith("The researcher is in")]))
    climates = set().union(*(CLIMATE_OF.get(r, set()) for r in regions)) if regions else set()
    return Setting(
        places=places or named.places,
        regions=regions or named.regions,
        climates=climates,
        covers=named.covers,
    )


def where(geometries: list[dict]) -> str | None:
    """The line telling Magon where the areas lie: the mean of their outlines' vertices."""
    points = []
    for g in geometries:
        rings = g.get("coordinates") or []
        if g.get("type") == "MultiPolygon":
            rings = [ring for polygon in rings for ring in polygon]
        if g.get("type") == "Point":
            rings = [[rings]]
        for ring in rings:
            points += [p for p in ring if isinstance(p, list | tuple) and len(p) >= 2]
    if not points:
        return None
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return (
        f"The areas lie near {abs(lat):.2f}° {'N' if lat >= 0 else 'S'}, "
        f"{abs(lon):.2f}° {'E' if lon >= 0 else 'W'}."
    )


@dataclass
class Match:
    differs: list[str]  # the dimensions that differ, in words
    setting: Setting

    @property
    def elsewhere(self) -> bool:
        return bool(self.differs)


def compare(paper: Setting, here: Setting) -> Match:
    """Whether a paper's setting differs from the researcher's, on what both sides state."""
    differs = []
    if paper.regions and here.regions and not paper.worldwide and not paper.regions & here.regions:
        differs.append(f"made in {paper.describe().split(', on ')[0]}")
    foreign = paper.climates - here.climates if here.regions else set()
    if foreign and paper.climates and not paper.climates & here.climates:
        differs.append(f"in a {min(foreign)} climate")
    if paper.covers and here.covers:
        mine = set().union(*(ALIKE.get(c, {c}) for c in here.covers))
        if not set(paper.covers) & mine:
            differs.append(f"on {paper.covers[0]}")
    return Match(differs, paper)


def line(n: int, match: Match) -> str:
    """What the model is told of a paper's setting, under its abstract."""
    said = match.setting.describe()
    if match.elsewhere:
        return (
            f"Setting of [{n}]: {said}. Not the researcher's setting ({'; '.join(match.differs)}): "
            "use it only for the direction of an effect, and say where it was found."
        )
    return f"Setting of [{n}]: {said}." if said else ""


# a citation group, like [2] or [1, p. 4; 3]
CITATION = re.compile(r"\[(\d+(?:\s*,\s*p\.\s*\d+)?(?:\s*[,;]\s*\d+(?:\s*,\s*p\.\s*\d+)?)*)\]")


def named(sentence: str, s: Setting) -> bool:
    """Whether a sentence already says where the study was made, or on what."""
    words = s.places + sorted(s.regions) + s.covers + sorted(s.climates)
    words += [a for a, p in ADJECTIVES.items() if p in s.places]
    return any(re.search(rf"\b{re.escape(w)}", sentence, re.IGNORECASE) for w in words if w)


def found(said: str) -> str:
    """Where a paper was made, in words: found in India, on rice; found on cereals; found elsewhere."""
    if not said:
        return "found elsewhere"
    return f"found {said}" if said.startswith("on ") else f"found in {said}"


def name_settings(text: str, matches: dict[int, Match]) -> tuple[str, list[dict]]:
    """Add, after the citation of a paper made elsewhere, where it was made, in sentences that
    use it without saying so. Returns the text and what was added."""
    from engine.honesty import sentences

    added: list[dict] = []
    out, last = [], 0
    for start, end, sentence in sentences(text):
        for m in CITATION.finditer(sentence):
            cited = [int(x) for x in re.split(r"[,;]", m.group(1)) if x.strip().isdigit()]
            away = [n for n in cited if n in matches and matches[n].elsewhere]
            if not away or any(named(sentence, matches[n].setting) for n in away):
                continue
            said = "; ".join(found(matches[n].setting.describe()) for n in away)
            at = start + m.end()
            out.append(text[last:at])
            out.append(f" ({said})")
            last = at
            added.append({"cites": away, "setting": said, "sentence": sentence.strip()})
            break  # once a sentence
    out.append(text[last:])
    return "".join(out), added
