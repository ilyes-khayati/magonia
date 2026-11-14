"""Sentences Magon cannot stand behind, found by code: what it says that nothing it was given
could back, and what it says that is known to be false.

The other checks compare an answer with what Magon was given: passages, facts, papers. They
are blind where nothing was given. Tested by researchers on 14 November 2026, Magon
summarised a paper that does not exist, "Ben Salah et al. (2019)", without searching, and said
"a search of the literature did not yield any relevant papers" when no search had run. A
third failure was a definition turned upside down: "higher SPEI values correspond to drier
conditions". Each is a sentence code can recognise:

- a paper named by its author and year that matches no paper found: the reference is
  invented, and so is what the sentence says it found
- a sentence about a search or a reading when none was made: Magon misreporting its own
  actions
- a statement that inverts the sign of a variable whose meaning is fixed: higher SPEI is
  wetter, higher LST is hotter

These sentences are withdrawn whatever the setting for unsupported statements, because they
are not unsupported but contradicted: by the list of papers found, by the record of what
Magon did, or by the definition of the variable.
"""

import re

from engine.citations import GROUP
from engine.support import NOT_AN_END, SENTENCE, Statement

# A paper named by its first author and year, in the forms a model writes: "Ben Salah et al.
# (2019)", "Smith and Jones (2020)", "Smith (2018)", "(Smith et al., 2019)", "Smith et al.,
# 2019". The surname is the last capitalised word before "et al", "and" or the year.
NAME = r"[A-Z][A-Za-zÀ-ÿ'’\-]+"
YEAR = r"(?:19|20)\d\d"
MENTION = re.compile(
    # "Ben Salah et al. (2019)", "Smith et al., 2019", "Smith and Jones (2020)", "Smith (2018)";
    # a place and a year ("Béja, 2024", "Tunisia 2022") is not a reference, so a bare name
    # needs the year in parentheses
    rf"\b(?P<name>{NAME})(?:\s+et\s+al\.?,?\s*\(?|\s+(?:and|&)\s+{NAME},?\s*\(?|\s+\()"
    rf"(?P<year>{YEAR})"
    # "(Smith, 2018)", "(Smith et al. 2019)"
    rf"|(?<=\()(?P<name2>{NAME})(?:\s+et\s+al\.?)?,?\s+(?P<year2>{YEAR})"
)
# A sentence that says a paper was not found is the right answer, not an invented reference
DENIAL = re.compile(
    r"\b(could ?n[o']t|cannot|can't|did ?n[o']t|unable to|no record|not (be )?found|"
    r"does ?n[o']t (seem to )?exist|not able to|no (such )?(paper|study|publication))\b",
    re.IGNORECASE,
)
# Capitalised words that precede a year without naming an author
NOT_AUTHORS = {
    "In",
    "By",
    "Since",
    "From",
    "Until",
    "Before",
    "After",
    "During",
    "Between",
    "Of",
    "On",
    "The",
    "Spring",
    "Summer",
    "Autumn",
    "Fall",
    "Winter",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Sept",
    "Oct",
    "Nov",
    "Dec",
    "NDVI",
    "LST",
    "SPEI",
    "EVI",
    "SAVI",
    "MODIS",
    "Landsat",
    "Sentinel",
    "Tunisia",
    "Fig",
    "Figure",
    "Table",
    "Year",
    "Years",
    "To",
    "And",
    "Or",
    "At",
    "For",
    "As",
    "Over",
    "About",
}

# What Magon says it did: searched, read, looked something up
SEARCHED = re.compile(
    r"\b(I|we)\s+(have\s+)?(searched|looked up|looked for|queried|ran a search|found no|"
    r"did not find|didn't find|could not find|couldn't find)"
    r"|\b(a|my|the|this|our)\s+(literature\s+)?search\b"
    r"|\bsearch(ing)?\s+(of\s+)?the\s+literature\b"
    r"|\bdid not (yield|return|find)\b|\b(yielded|returned|found) no\b"
    # the tool written out as text: 'Search_papers("olive hail") yielded no results' (14 Nov)
    r"|\bsearch_papers\b",
    re.IGNORECASE,
)

# Between the variable and the word that would invert it, a contrast means the sentence gives
# both directions: "positive SPEI values indicate wetter conditions, while negative values
# indicate drier ones" is right, and was withdrawn as wrong (14 Nov)
CONTRAST = re.compile(
    r"\b(wet|wetter|dry|drier|while|whereas|but|negative|positive|lower|low|higher|high|"
    r"less|more|conversely|opposite|hotter|warmer)\b|;",
    re.IGNORECASE,
)


def upside_down(sentence: str) -> str:
    """The definition a sentence turns upside down, or "" when it does not."""
    for pattern, fact in UPSIDE_DOWN:
        for match in pattern.finditer(sentence):
            between = match.group(0)[len(match.group(1)) :]
            # the words after the variable, up to the inverting word, not including it
            between = between[: between.lower().rfind(match.group(match.lastindex).lower())]
            if not CONTRAST.search(between):
                return fact
    return ""


# A variable whose direction is fixed by its definition, written the wrong way round
UPSIDE_DOWN = [
    (
        re.compile(
            r"\b(higher|high|increas\w*|rising|positive|larger|greater)\s+(values?\s+of\s+)?"
            r"SPEI\b[^.;]{0,80}?\b(drier|dry|drought|water deficit)",
            re.IGNORECASE,
        ),
        (
            "SPEI: higher values mean wetter conditions, lower (negative) values drier ones "
            "(Vicente-Serrano et al., 2010)."
        ),
    ),
    (
        re.compile(
            r"\b(lower|low|decreas\w*|falling|negative|smaller)\s+(values?\s+of\s+)?"
            r"SPEI\b[^.;]{0,80}?\b(wetter|wet|humid)",
            re.IGNORECASE,
        ),
        (
            "SPEI: lower (negative) values mean drier conditions, higher values wetter ones "
            "(Vicente-Serrano et al., 2010)."
        ),
    ),
    (
        re.compile(
            r"\b(higher|high|increas\w*|rising)\s+(values?\s+of\s+)?LST\b[^.;]{0,60}?"
            r"\b(cooler|colder)\b",
            re.IGNORECASE,
        ),
        "LST: higher values mean a hotter surface.",
    ),
]


def sentences(answer: str) -> list[tuple[int, int, str]]:
    """Every sentence of the answer, with its span, the dots of abbreviations kept whole."""
    masked = NOT_AN_END.sub(lambda m: m.group(0).replace(".", "\x00"), answer)
    out = []
    for match in SENTENCE.finditer(masked):
        sentence = answer[match.start() : match.end()]
        if sentence.strip():
            start = match.start() + len(sentence) - len(sentence.lstrip())
            out.append((start, match.end(), sentence.strip()))
    return out


def mentions(text: str) -> list[tuple[str, int]]:
    """The papers a text names by author and year: (surname, year)."""
    found = []
    for m in MENTION.finditer(text):
        name = m.group("name") or m.group("name2")
        year = m.group("year") or m.group("year2")
        if name in NOT_AUTHORS or name.isupper():
            continue
        found.append((name.lower(), int(year)))
    return found


def withdrawn(
    answer: str,
    papers: list,
    searched: bool,
) -> list[Statement]:
    """The sentences of an answer that are contradicted by what Magon knows, each with why.

    papers are those found or given (each with authors and year); searched says whether a
    literature search ran. A paper the researcher names is no more checkable than one the
    model names: describing a paper that was not found is the fake-paper trap, so only a
    sentence denying that it was found survives.

    What follows an invented reference describes it without naming it ("The research covers
    the Kairouan governorate…"), so every following sentence that cites nothing goes with it,
    until the answer cites a paper that was found.
    """
    known = {(p.authors[0].split()[-1].lower(), p.year) for p in papers if p.authors}
    out = []
    tainted = ""  # the invented reference the sentences that follow are about
    for start, end, sentence in sentences(answer):
        why = ""
        named = mentions(sentence)
        invented = [(n, y) for n, y in named if (n, y) not in known]
        cites_found = bool(GROUP.search(sentence)) or any(m in known for m in named)
        if invented and not DENIAL.search(sentence):
            name, year = invented[0]
            tainted = f"{name.title()} ({year})"
            why = (
                f"No paper by {tainted} was found. The reference cannot be checked, nor what "
                "the sentence says it found."
            )
        elif cites_found:
            tainted = ""
        elif tainted and not DENIAL.search(sentence):
            why = f"Describes {tainted}, a paper that was not found."
        elif not searched and SEARCHED.search(sentence):
            why = "No literature search was made for this answer."
        else:
            why = upside_down(sentence)
        if why:
            out.append(Statement(start, end, sentence, [], "unsupported", why, "Magonia's check"))
    return out


NOTE = (
    "{n} {what} withdrawn: {pronoun} contradicted what Magon can check (the papers found, "
    "what it did, or a definition)."
)


def note(n: int) -> str:
    return NOTE.format(
        n=n,
        what="statement was" if n == 1 else "statements were",
        pronoun="it" if n == 1 else "they",
    )
