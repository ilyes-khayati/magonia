"""How far a paper's setting is from the researcher's: a record of each paper, and a rating.

A finding made in one setting cannot be assumed to hold in another unless what moderates it is
the same there (Egami and Hartman 2023, APSR 117(3)). Evidence synthesis handles this as
indirectness: write down the target, compare each study with it, and for every difference judge
whether it could change the result; a difference lowers confidence rather than excluding the
study (Core GRADE 5, Guyatt et al. 2025, BMJ 389:e083865). Automated indirectness verdicts are
weak (F1 0.3-0.4 against 0.75-0.78 for risk of bias, Suster et al. 2023, JMIR), whereas the plain
facts a paper states, such as where it was made and on what, are read reliably (Konet et al.
2024, Res. Synth. Methods). So code reads the facts from the title and abstract, compares them
with the workspace field by field, and shows the comparison; it does not judge the science.

The rating, fixed before it was measured:
- near: the paper's region is the researcher's, and so is its vegetation (or a like kind).
- partly: one of the two matches and the other is not stated, or the region matches and the
  vegetation differs, or the vegetation matches in another region of the same climate.
- far: another region, with no climate in common stated; or, where the region is not stated,
  another vegetation or another climate.
- unknown: the abstract states neither where the study was made nor on what.
A worldwide study is general rather than near or far, and is rated partly.
"""

import re
from dataclasses import asdict, dataclass, field

from engine import setting

# what a study measured from: the platform or instrument named in its abstract
SENSORS: dict[str, str] = {
    r"\bMODIS\b|\bMOD13\w*|\bMOD11\w*|\bMYD\w+": "MODIS",
    r"\bLandsat\b|\bHLS\w*": "Landsat",
    r"\bSentinel[- ]?2\b|\bS2\b": "Sentinel-2",
    r"\bSentinel[- ]?1\b|\bSAR\b": "radar",
    r"\bAVHRR\b|\bGIMMS\b|\bNOAA\b": "AVHRR",
    r"\bSPOT[- ]?VEG\w*|\bSPOT\b": "SPOT",
    r"\bPlanetScope\b": "PlanetScope",
    r"\bUAVs?\b|\bdrones?\b|\bunmanned aerial\b": "UAV",
    r"\bLiDAR\b|\bGEDI\b": "LiDAR",
    r"\bphenocams?\b|\bdigital (repeat )?(photograph|camera)\w*": "ground camera",
    r"\bin situ\b|\bfield (measurements?|plots?|data)\b|\beddy covariance\b": "field data",
}
# what it measured: the variables a researcher in Magonia works with, and their kin
VARIABLES: dict[str, str] = {
    r"\bNDVI\b|\bnormali[sz]ed difference vegetation index\b": "NDVI",
    r"\bEVI\b|\bSAVI\b|\bNDMI\b|\bNDWI\b|\bVHI\b|(?<!difference )\bvegetation ind(ex|ices)\b": (
        "other vegetation index"
    ),
    r"\bLST\b|\bland surface temperature\b|\bsurface temperature\b": "LST",
    r"\bSPEI\b|\bSPI\b|\bPDSI\b|\bdrought index\b": "drought index",
    r"\bprecipitation\b|\brainfall\b": "rainfall",
    r"\bevapotranspiration\b|\bET\b": "evapotranspiration",
    r"\bGPP\b|\bgross primary product\w*|\bbiomass\b": "productivity",
    r"\byields?\b": "yield",
}


HEADING = "**Does the evidence fit your setting"  # begins the part code writes


@dataclass
class Record:
    """What code could read of a paper: where, in what climate, on what, from what, of what."""

    setting: setting.Setting
    sensors: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)


@dataclass
class Fit:
    """How a paper's setting compares with the researcher's, field by field."""

    level: str  # near, partly, far or unknown
    paper: str  # the paper's setting in a few words, e.g. "India, on rice"
    same: list[str] = field(default_factory=list)  # e.g. "region (the Mediterranean)"
    differs: list[str] = field(default_factory=list)  # e.g. "region (East Asia, not ...)"
    unstated: list[str] = field(default_factory=list)  # fields the abstract does not state

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def usable(self) -> bool:
        """Whether its findings may be offered as an explanation of the researcher's data."""
        return self.level in ("near", "partly")


def found(patterns: dict[str, str], text: str) -> list[str]:
    hits = [name for pattern, name in patterns.items() if re.search(pattern, text, re.IGNORECASE)]
    return list(dict.fromkeys(hits))


def record_of(paper) -> Record:
    text = f"{paper.title or ''}. {paper.abstract or ''}"
    return Record(setting.read(text), found(SENSORS, text), found(VARIABLES, text))


def alike(kinds: list[str]) -> set[str]:
    return set().union(*(setting.ALIKE.get(k, {k}) for k in kinds)) if kinds else set()


def rate(record: Record, here: setting.Setting) -> Fit:
    """Compare a paper's record with the researcher's setting (the rule in the module's doc)."""
    s = record.setting
    fit = Fit(level="unknown", paper=s.describe() or "not stated")
    region = None  # True: same region; False: another; None: not stated
    if s.worldwide and not s.regions:
        fit.same.append("worldwide study")
    elif s.regions and here.regions:
        region = bool(s.regions & here.regions)
        names = ", ".join(sorted(s.regions))
        if region:
            fit.same.append(f"region ({names})")
        else:
            fit.differs.append(f"region ({names}, not {', '.join(sorted(here.regions))})")
    else:
        fit.unstated.append("region")
    climate = None
    if s.climates and here.climates:
        climate = bool(s.climates & here.climates)
        names = ", ".join(sorted(s.climates))
        (fit.same if climate else fit.differs).append(f"climate ({names})")
    elif here.climates:
        fit.unstated.append("climate")
    vegetation = None
    if s.covers and here.covers:
        vegetation = bool(set(s.covers) & alike(here.covers))
        if vegetation:
            fit.same.append(f"vegetation ({s.covers[0]})")
        else:
            fit.differs.append(f"vegetation ({s.covers[0]}, not {here.covers[0]})")
    elif here.covers:
        fit.unstated.append("vegetation")

    if s.worldwide and not s.regions:
        fit.level = "partly"
    elif region and vegetation:
        fit.level = "near"
    elif not climate and (
        region is False or (region is None and (vegetation is False or climate is False))
    ):
        fit.level = "far"
    elif region or vegetation or climate:
        fit.level = "partly"
    return fit


def line(n: int, rec: Record, fit: Fit) -> str:
    """What the model is told under a paper: its record and how it fits the researcher's."""
    measured = ", ".join(rec.variables) or "not stated"
    sensors = ", ".join(rec.sensors) or "not stated"
    head = f"About [{n}]: made in {fit.paper}; measured {measured}; from {sensors}."
    if fit.level == "near":
        return f"{head} Fit to the researcher's setting: near ({'; '.join(fit.same)})."
    if fit.level == "partly":
        return (
            f"{head} Fit to the researcher's setting: partly ({'; '.join(fit.same + fit.differs)}"
            "). Its findings may explain their data only as a possibility, with that said."
        )
    if fit.level == "far":
        return (
            f"{head} Fit to the researcher's setting: far ({'; '.join(fit.differs)}). Use it only "
            "to say what was found there, never as an explanation of the researcher's data."
        )
    return f"{head} Fit to the researcher's setting: unknown (the abstract does not say where)."


def summary(cited: dict[int, tuple[str, Record, Fit]], here: setting.Setting) -> str:
    """The part of the answer, written by code, that says whether the evidence fits.

    `cited` maps each paper the answer cites to its short name, record and fit."""
    if not cited:
        return ""
    target = here.describe() or "your setting"
    lines = [f"{HEADING} ({target})?**"]
    for n, (short, _, fit) in sorted(cited.items()):
        if fit.level == "near":
            said = f"near: {'; '.join(fit.same)}."
        elif fit.level == "partly":
            said = f"partly: {'; '.join(fit.same + fit.differs)}."
        elif fit.level == "far":
            said = f"far: {'; '.join(fit.differs)}. What it found is not shown to hold here."
        else:
            said = "unknown: the abstract does not say where the study was made."
        lines.append(f"- [{n}] {short} ({fit.paper}) — {said}")
    if not any(fit.usable for _, _, fit in cited.values()):
        lines.append(
            "None of the papers cited was made in a setting like yours, so none of them explains "
            "your data; at most they show what was found elsewhere."
        )
    return "\n".join(lines)
