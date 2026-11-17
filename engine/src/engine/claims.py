"""A claim from a paper, tested on the researcher's own data (issue #171).

A paper says "olive NDVI responds to drought with a lag of about 12 months". Whether that
holds where the researcher works is a question their own series can answer, with an analysis
Magonia already has. So a claim is read by code into what it asserts, tested with that
analysis on the researcher's area, and given one of four verdicts by fixed rules:

- replicates: the analysis finds what the claim says, beyond chance and with its sign
- contradicts: it finds the opposite, beyond chance
- undecided: it finds nothing beyond chance where the claim points (and says what it does find)
- cannot test: the claim is not of a kind Magonia can test, or the data are not open

Two kinds of claim are tested:

- a driver acting on vegetation, perhaps with a delay ("drought lowers NDVI a year later"):
  the correlation of the two series' anomalies at lags 1 to 12 months, or up to the claimed
  lag, against a bound corrected for autocorrelation and for testing several lags (lags.py,
  as in the paper's notebook 03). A claimed lag is matched within one month either side, and
  the strongest of those lags is the one judged.
- a long-term change ("NDVI has declined since 2000"): the Theil–Sen slope of the annual means
  and the Mann–Kendall test (trend.py).

The claim is read by code, not by the language model: what it asserts must not depend on a
model that can misread a sign, as Magon did with SPEI (14 November). The reading is shown with
the verdict, so the researcher sees what was tested and can disagree with it.

What a verdict does not say: that the paper was right or wrong. A claim made for one place
and period is tested on another; "contradicts" means it does not hold here.
"""

import re
from dataclasses import asdict, dataclass, field

import numpy as np

from engine.facts import Series, View, monthly_series
from engine.lags import EXPECTED, deseasonalise, driver_evidence
from engine.proposals import named
from engine.trend import trend

VEGETATION = ["ndvi", "evi", "savi", "ndmi", "lai", "fpar", "gpp"]
DRIVERS = ["spei", "lst", "air_temperature", "rain", "soil_moisture", "et"]
ALPHA = 0.05
MAX_LAG = 36  # months: a claimed lag beyond three years is not tested
NEAR = 1  # months either side of a claimed lag that count as the claimed lag

LOWERS = re.compile(
    r"\b(reduc\w*|decreas\w*|lower\w*|declin\w*|loss|lost|los(e|es|ing)|drop\w*|fall\w*|fell|"
    r"negativ\w*|harm\w*|suppress\w*|brown\w*|stress\w*|damag\w*)\b",
    re.IGNORECASE,
)
RAISES = re.compile(
    r"\b(increas\w*|rais\w*|higher|positiv\w*|enhanc\w*|boost\w*|green(er|ing)|"
    r"improv\w*|ris(e|es|ing)|rose)\b",
    re.IGNORECASE,
)
NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1,
}  # fmt: skip
COUNT = r"\d{1,2}|" + "|".join(NUMBERS)
LAG = re.compile(rf"\b({COUNT})(?:\s*(?:-|–|to)\s*({COUNT}))?[\s-]*months?\b", re.IGNORECASE)
YEAR_LAG = re.compile(
    r"\b(a|one|1)[\s-]*year\b|\b(previous|following|next) year\b|\bthe year (before|after)\b"
    r"|\bannual lag\b",
    re.IGNORECASE,
)
# A word that says which way the driver moves, just before it: "higher LST", "less rain".
# Read apart from the verb, so "higher LST reduces NDVI" is a negative link, not none
DRIVER_WORDS = r"lst|spei|temperature|heat|rain\w*|precipitation|drought|soil moisture|aridity"
DRIVER_MOVES = re.compile(
    rf"\b(?P<way>higher|lower|more|less|increas\w*|decreas\w*|rising|falling|warmer|hotter|"
    rf"cooler|wetter|drier|stronger|weaker)\s+(?:\w+\s+){{0,2}}?(?:{DRIVER_WORDS})\b",
    re.IGNORECASE,
)
DRIVER_DOWN = re.compile(r"^(lower|less|decreas\w*|falling|cooler|drier|weaker)$", re.IGNORECASE)


RAIN_FALLS = re.compile(r"\b(fell|falls?|fallen|falling)\b", re.IGNORECASE)
DRY = re.compile(r"\b(drought|dry|drier|aridity|water deficit)\b", re.IGNORECASE)
# Not a finding a series can test: a link denied ("was not observed in the 12-month range")
# is easily read as the link itself, and a sentence about methods ("linear metrics alone are
# insufficient") claims nothing about the data (both from Bounouh 2024)
#
# Following VeriScore (Song et al. 2024), only what can be checked is checked: of the sentences
# in paper abstracts that name vegetation and a driver, most were not findings (measured on 20
# sentences labelled by hand, 15 Nov: 1 of 12 refused). Besides denials and methods, these are:
# - what was done or why: "correlation analysis was used to determine…", "quantifying the
#   response is crucial", "the results add insights"
# - a comparison between places or vegetation types: "arid regions showed the strongest
#   response", "vegetation loss in areas experiencing intensive land use". One series cannot
#   test a difference between series
# - an absence: "there was no evidence that winter rain reduces NDVI"
NOT_A_FINDING = re.compile(
    r"\b(not|no|never|neither|nor)\s+(\w+\s+){0,2}(observed|found|captured|detected|"
    r"significant|correlat\w*|affect\w*|related|linked)\b"
    r"|\b(metrics?|methods?|methodolog\w*|approach(es)?|insufficient|inappropriate)\b"
    r"|\b(was|were|is|are) (used|considered|applied|employed|derived|calculated|obtained)\b"
    r"|\bto (determine|assess|quantify|investigate|explore|understand|evaluate|examine)\b"
    r"|\b(quantifying|understanding|monitoring) [^.]{0,60}\b(is|are) (crucial|essential|"
    r"important|key|needed)\b|\b(add|adds|provide|provides) (more |new )?(insights?|support)\b"
    r"|\bguide the development\b|\b(RMSE|root mean squared? error|accuracy)\b"
    r"|\b(strongest|weakest|most sensitive|least sensitive|in comparison (to|with))\b"
    r"|\b(in|within) (the )?(areas|regions|sites|zones|places) (experiencing|with|where|that)\b"
    r"|\bno evidence\b",
    re.IGNORECASE,
)
# A finding links vegetation to something: without one of these words a sentence names the
# variables ("three products are considered: NDVI, SWI and LST") but says nothing about them
RELATION = re.compile(
    r"\b(correlat\w*|respon\w*|reduc\w*|decreas\w*|increas\w*|lower\w*|rais\w*|declin\w*|"
    r"affect\w*|impact\w*|effects?|control\w*|driv(e|es|en|er|ers|ing)|depend\w*|sensitiv\w*|"
    r"limit\w*|linked|associated|explain\w*|coupled|influenc\w*|stress\w*|harm\w*|"
    r"suppress\w*|enhanc\w*|boost\w*|improv\w*|ris(e|es|ing)|rose|fell|fall\w*|drop\w*|"
    r"lag\w*|loss|lost|green(er|ing))\b",
    re.IGNORECASE,
)
# The sign of a correlation stated outright: "positive correlations between the NDVI and the
# SPEI during dry summers" is NDVI rising with SPEI, whatever else the sentence says of drought
STATED_SIGN = re.compile(
    r"\b(?P<sign>positiv|negativ)\w*\s+(\w+\s+){0,3}?correlat\w*"
    r"|\bcorrelat\w*\s+(\w+\s+){0,2}?(?P<sign2>positiv|negativ)\w*",
    re.IGNORECASE,
)
# the driver named by its own name, not as drought
NAMED_DRIVER = re.compile(r"\b(spei|spi|precipitation|rain\w*|soil moisture)\b", re.IGNORECASE)


def count(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word.lower()]


TREND = re.compile(
    r"\b(trend\w*|since (19|20)\d\d|over (the )?(last|past) \d+|decades?|long[- ]term|"
    r"between (19|20)\d\d and (19|20)\d\d|per year|yr\s*[−-]1|"
    r"has (been )?(declin|increas|decreas|risen|fallen|grown)\w*)\b",
    re.IGNORECASE,
)
# Asking for a claim to be tested on the researcher's own data
ASKS = re.compile(
    r"\b(test|check|verify|try)\b[^.?!]{0,40}\b(claim|finding|statement|hypothesis|result)\b"
    r"|\b(does|do|would|could) (this|that|it|the (claim|finding|result))\b[^?]{0,60}"
    r"\b(hold|replicate|apply|be true|work)\b",
    re.IGNORECASE,
)
QUOTED = re.compile(r"[\"“«]([^\"”»]{12,400})[\"”»]")


@dataclass
class Claim:
    text: str  # as the paper or the researcher wrote it
    kind: str  # lag or trend
    response: str  # the vegetation variable
    driver: str | None = None
    sign: int | None = None  # of the link (response with driver) or of the trend
    sign_from: str = ""  # "claim" when the claim states it, "physics" when expected
    lag: int | None = None  # months, when the claim gives one

    def reading(self) -> str:
        """What was tested, in words, so the researcher can check the reading."""
        if self.kind == "trend":
            way = {1: "rises", -1: "falls", None: "changes"}[self.sign]
            return f"{self.response.upper()} {way} over the years"
        way = {1: "rises with", -1: "falls with", None: "follows"}[self.sign]
        plural = "s" if self.lag and self.lag > 1 else ""
        when = f" {self.lag} month{plural} earlier" if self.lag else " in the months before"
        return f"{self.response.upper()} {way} {self.driver.upper()}{when}"


@dataclass
class ClaimTest:
    claim: Claim
    verdict: str  # replicates, contradicts, undecided or cannot test
    area: str = ""
    summary: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {**asdict(self), "reading": self.claim.reading()}


def asks_to_test(message: str) -> bool:
    return bool(ASKS.search(message))


def claim_in(message: str) -> str:
    """The claim a message asks to test: quoted, or after a colon, or the message itself."""
    if quoted := QUOTED.search(message):
        return quoted.group(1).strip()
    if ":" in message:
        after = message.split(":", 1)[1].strip()
        if len(after.split()) >= 4:
            return after
    return message.strip()


DRIVER_NAMES = {
    "spei": r"spei|spi|drought",
    "lst": r"lst|land surface temperature|temperature",
    "air_temperature": r"air temperature|temperature",
    "rain": r"rain\w*|precipitation",
    "soil_moisture": r"soil moisture",
    "et": r"et|evapotranspiration",
}


def said_of(driver: str, text: str) -> int:
    """The sign of a correlation stated outright for this driver, or 0. "NDVI is negatively
    correlated with LST and positively correlated with SPEI" gives -1 for LST, 1 for SPEI:
    each sign is the one whose words, up to the next sign, name the driver."""
    found = list(STATED_SIGN.finditer(text))
    for k, match in enumerate(found):
        end = found[k + 1].start() if k + 1 < len(found) else len(text)
        if re.search(rf"\b({DRIVER_NAMES[driver]})\b", text[match.start() : end], re.IGNORECASE):
            word = (match.group("sign") or match.group("sign2")).lower()
            return 1 if word == "positiv" else -1
    return 0


def read(text: str) -> Claim | None:
    """What a claim asserts, or None when it is not one Magonia can test."""
    variables = named(text)
    response = next((v for v in variables if v in VEGETATION), None)
    if response is None and re.search(r"\b(vegetation|greenness|canopy)\b", text, re.IGNORECASE):
        response = "ndvi"
    if response is None or NOT_A_FINDING.search(text) or not RELATION.search(text):
        return None
    driver = next((v for v in variables if v in DRIVERS), None)
    # the way the driver moves ("higher LST") is read apart from what it does ("reduces NDVI")
    moved = DRIVER_MOVES.search(text)
    rest = DRIVER_MOVES.sub(" ", text) if moved else text
    if driver == "rain":
        rest = RAIN_FALLS.sub(" ", rest)  # "the rain which fell": rain falling, not a decrease
    lowers, raises = bool(LOWERS.search(rest)), bool(RAISES.search(rest))
    effect = -1 if lowers and not raises else 1 if raises and not lowers else None
    if moved and effect is not None and DRIVER_DOWN.match(moved.group("way")):
        effect = -effect  # "less rain lowers NDVI": NDVI rises with rain

    if driver is None:
        # a change with no direction ("moving to a more constant seasonal behaviour"), or
        # both ("7.6% negative and 11.8% positive NDVI trends"), is not one change to test
        if not TREND.search(text) or effect is None:
            return None
        return Claim(text, "trend", response, sign=effect, sign_from="claim" if effect else "")

    lag = None
    if found := LAG.search(text):
        low, high = count(found.group(1)), found.group(2)
        lag = round((low + count(high)) / 2) if high else low
    elif YEAR_LAG.search(text):
        lag = 12
    if lag is not None and not 1 <= lag <= MAX_LAG:
        lag = None

    # Drought is low SPEI: "drought lowers NDVI", "when SPEI indicates drier conditions NDVI
    # decreases" (Bounouh 2024) and "stronger drought reduces greenness" all mean NDVI rises
    # with SPEI. Said of drought rather than of SPEI's own value, the sign turns over; the
    # same holds for rain and soil moisture ("a decrease in vegetation due to drier years")
    sign = effect
    stated = said_of(driver, text)
    if stated and (driver not in ("spei", "rain", "soil_moisture") or NAMED_DRIVER.search(text)):
        return Claim(text, "lag", response, driver, stated, "claim", lag)
    if sign is not None and driver in ("spei", "rain", "soil_moisture"):
        drought_moved = moved and re.search(r"drought|aridity", moved.group(0), re.IGNORECASE)
        said_dry = DRY.search(text) and not moved
        if drought_moved or said_dry:
            sign = -sign
    if sign is None:
        return Claim(text, "lag", response, driver, EXPECTED.get(driver), "physics", lag)
    return Claim(text, "lag", response, driver, sign, "claim", lag)


def series_for(view: View, key: str, area: str | None = None) -> Series | None:
    return next((s for s in view.series if s.key == key and (area is None or s.area == area)), None)


def test(claim: Claim, view: View) -> ClaimTest:
    """The claim tested on the first open area that has the series it needs."""
    for area in dict.fromkeys(s.area for s in view.series):
        response = series_for(view, claim.response, area)
        driver = series_for(view, claim.driver, area) if claim.driver else None
        if response is None or (claim.driver and driver is None):
            continue
        if claim.kind == "trend":
            return trend_test(claim, response)
        return lag_test(claim, response, driver)
    needed = " and ".join(v.upper() for v in (claim.response, claim.driver) if v)
    return ClaimTest(
        claim,
        "cannot test",
        summary=[f"No open area has {needed}: open them on the Data page to test this claim."],
    )


def lag_test(claim: Claim, response: Series, driver: Series) -> ClaimTest:
    y = deseasonalise(monthly_series(response))
    x = deseasonalise(monthly_series(driver))
    longest = max(12, (claim.lag or 0) + NEAR)
    found = driver_evidence(y, x, driver.title, driver.key, max_lag=longest)
    r = found.r
    if claim.lag:
        window = range(max(1, claim.lag - NEAR), min(longest, claim.lag + NEAR) + 1)
        at = max(window, key=lambda k: abs(r[k - 1]) if not np.isnan(r[k - 1]) else -1)
    else:
        at = found.lag
    value = r[at - 1]
    beyond = abs(value) > found.bound
    agrees = claim.sign is None or np.sign(value) == claim.sign
    if beyond and agrees:
        verdict = "replicates"
    elif beyond:
        verdict = "contradicts"
    else:
        verdict = "undecided"
    who = f"{response.area}: {response.title} anomalies and {driver.title} anomalies"
    where = f"{at} month{'s' if at > 1 else ''} earlier"
    stats = f"r = {value:.2f}, bound ±{found.bound:.2f} over lags 1 to {longest}"
    expected = {1: "positive", -1: "negative"}.get(claim.sign, "")
    told = (
        f" ({expected}, as the claim says)"
        if claim.sign_from == "claim"
        else (f" ({expected}, the physical expectation)" if expected else "")
    )
    lines = [f"Tested: {claim.reading()}{told}."]
    if verdict == "replicates":
        lines.append(f"{who}: at {where} {stats}; beyond chance with the claimed sign.")
    elif verdict == "contradicts":
        lines.append(f"{who}: at {where} {stats}; beyond chance, with the opposite sign.")
    else:
        lines.append(f"{who}: at {where} {stats}; not beyond chance.")
        if found.decision == "stands out" and found.lag != at:
            months = f"{found.lag} month{'s' if found.lag > 1 else ''}"
            lines.append(f"The lag that does stand out is {months} (r = {found.best:.2f}).")
    if driver.key == "spei":
        lines.append(
            f"Drought is measured here as {driver.title}, one accumulation scale; the claim may "
            "rest on another."
        )
    lines.append("A verdict on this area and period, not on the paper.")
    return ClaimTest(
        claim,
        verdict,
        response.area,
        lines,
        {
            "r": r,
            "bound": found.bound,
            "lag": at,
            "strongest_lag": found.lag,
            "response": response.title,
            "driver": driver.title,
            "months": int(y.notna().sum()),
        },
    )


def trend_test(claim: Claim, response: Series) -> ClaimTest:
    found = trend(response.area, response.title, response.key, response.units, response.points)
    if found.slope is None or found.p is None:
        return ClaimTest(claim, "cannot test", response.area, found.summary)
    beyond = found.p < ALPHA
    agrees = claim.sign is None or np.sign(found.slope) == claim.sign
    verdict = "replicates" if beyond and agrees else "contradicts" if beyond else "undecided"
    lines = [f"Tested: {claim.reading()}.", *found.summary, *found.cautions]
    return ClaimTest(
        claim,
        verdict,
        response.area,
        lines,
        {"slope_per_decade": found.slope, "p": found.p, "years": len(found.years)},
    )


# What each verdict means, said for the model: left to explain it, Magon wrote that a claim
# that replicated "shows the opposite of the claim" (14 Nov)
MEANING = {
    "replicates": "the researcher's data show what the claim says",
    "contradicts": "the researcher's data show the opposite of what the claim says",
    "undecided": "the researcher's data show nothing beyond chance where the claim points",
    "cannot test": "Magonia cannot test this claim with what is open",
}


def block(result: ClaimTest) -> str:
    """The result as Magon is given it: it reports the verdict, it does not reach one."""
    lines = "\n".join(f"- {line}" for line in result.summary)
    return (
        f'Magonia tested the claim "{result.claim.text}" on the researcher\'s data. '
        f"Verdict, decided by code: {result.verdict.upper()}, which means "
        f"{MEANING[result.verdict]}.\n{lines}\n"
        "Report this verdict and what it means in these words, with the numbers as given. Use "
        "only the numbers of these lines for the claim, not other facts. Say what was tested, "
        "and that it holds or not for this area and period, not for the paper's."
    )


# advice to the researcher, not an explanation (seen 17 Nov: "To test these possibilities,
# consider analyzing the correlation between LST and NDVI" was read as a claim)
ADVICE = re.compile(
    r"\b(consider|you (could|may|might|can|should)|we (suggest|recommend)|it would be (useful|"
    r"worth)|to test (this|these|it)|further (analysis|research|study))\b",
    re.IGNORECASE,
)


def tests_of(text: str, view: View, limit: int = 4) -> list[ClaimTest]:
    """The explanations in an answer that code can test, each tested once on the open data.

    An explanation offered for the researcher's data ("drought lowers NDVI two months later")
    is a claim like one from a paper: read by code, tested with the same rules. Sentences that
    are not a testable claim, or that need series that are not open, are left out."""
    from engine.honesty import sentences

    done: dict[str, ClaimTest] = {}
    for _, _, sentence in sentences(text):
        if ADVICE.search(sentence):
            continue  # "consider analysing NDVI against SPEI" proposes a test, it claims nothing
        claim = read(re.sub(r"\[[^\]]*\]|\*\*", "", sentence))
        if claim is None or claim.reading() in done:
            continue
        result = test(claim, view)
        if result.verdict != "cannot test":
            done[claim.reading()] = result
        if len(done) >= limit:
            break
    return list(done.values())


def tested_part(results: list[ClaimTest]) -> str:
    """The part of the answer, written by code, that gives each explanation's test."""
    if not results:
        return ""
    lines = ["**Tested on your data** (by code, on this area and period):"]
    for r in results:
        first = next((x for x in r.summary if not x.startswith("Tested:")), "")
        lines.append(f"- {r.claim.reading()}: {r.verdict}. {first}".rstrip())
    return "\n".join(lines)
