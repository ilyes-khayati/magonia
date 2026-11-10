"""What Magonia's interface has, in one place: told to Magon, and checked in its answers.

Magon has sent researchers to buttons that do not exist ("click the Seasonal Plot button").
The pages, analyses and controls below are the ones the interface really has. Magon is given
this list; after an answer is written, every page, button, tab or analysis it names as a
control is looked for in it, and a name that is not there is flagged, so that a researcher is
never sent looking for something that was made up.

The analyses must stay the same as the interface's own list (web/src/analyses.ts); a test
compares them.
"""

import re
from dataclasses import asdict, dataclass

from engine.catalogue import CATALOGUE

PAGES = {
    "Map": "draw or import areas, and see layers",
    "Data": "the period, monthly or seasonal steps, cloud masking, gap filling and the SPEI "
    "scale; a chart per variable, with its average year and anomalies",
    "Analyses": 'relations between the variables, each added with "Add analysis"',
    "Model": "forecast experiments (Ridge, Random Forest, XGBoost, and the networks MLP, LSTM, "
    "GRU, TCN), what each model leans on, and whether that holds across training years",
    "Board": "pinned cards and notes",
    "Library": "the researcher's PDFs and standing instructions",
    "Settings": "the theme, Earth Engine, and how Magon answers",
}
ANALYSES = [
    "Correlation and lag",
    "Trend and season",
    "Long-term trend",
    "Season dates",
    "Memory and lags",
    "Drought scale and lag",
    "Wavelet coherence",
    "Wavelet leakage audit",
    "Pixel purity",
]
CONTROLS = [
    "Add analysis",
    "Add another analysis",
    "New experiment",
    "Duplicate",
    "Pin",
    "Pin to the board",
    "Unpin",
    "Notebook",
    "Compare",
    "CSV",
    "Add a section",
    "Add a note",
    "Recipe",
    "Native",
    "Monthly",
    "Seasonal",
    "Mean",
    "Median",
]
# what an answer may say to present a name as part of the interface
KINDS = r"button|tab|menu|panel|page|option|tool|feature|toggle|card|analysis|section|view|mode"
# a name in quotes or bold, then what kind of control it is: "Seasonal Plot" button
MENTION = re.compile(
    r"(?:\*\*|[\"“'‘])(?P<name>[A-Z][^\"”’*\n]{1,40}?)(?:\*\*|[\"”'’])\s+(?P<kind>"
    + KINDS
    + r")s?\b"
    r"|\bthe\s+(?P<bare>(?:[A-Z][\w-]*\s){1,4})(?P<bkind>" + KINDS + r")s?\b"
)


@dataclass
class Mention:
    start: int
    end: int
    text: str  # the name as written
    kind: str  # button, page, tab…
    status: str  # known, or unknown when the interface has nothing by that name

    def to_dict(self) -> dict:
        return asdict(self)


def known_names() -> set[str]:
    variables = {v.name for v in CATALOGUE.values()} | {k.upper() for k in CATALOGUE}
    return {n.lower() for n in [*PAGES, *ANALYSES, *CONTROLS, *variables, "Magon", "Magonia"]}


def is_known(name: str, names: set[str]) -> bool:
    """Known only when it is exactly one of the interface's names, or a variable's chart:
    "Seasonal Plot" is not "Seasonal", however close."""
    low = re.sub(r"\s+", " ", name.strip().lower())
    low = re.sub(r"^(the|a|an)\s+", "", low)
    low = re.sub(r"\s+(chart|series|map|layer)$", "", low)
    return low in names


def check_app(answer: str) -> list[Mention]:
    """Every name the answer presents as a page, button or analysis, known or not."""
    names = known_names()
    found = []
    for m in MENTION.finditer(answer):
        name = (m.group("name") or m.group("bare") or "").strip()
        kind = (m.group("kind") or m.group("bkind")).lower()
        if not name:
            continue
        status = "known" if is_known(name, names) else "unknown"
        found.append(Mention(m.start(), m.end(), name, kind, status))
    return found


def described() -> str:
    """The interface as Magon is told about it."""
    pages = "\n".join(f"- {name}: {what}." for name, what in PAGES.items())
    return (
        "What Magonia has (name only these pages, analyses and controls; there are no others):\n"
        f"{pages}\n"
        f"- The analyses: {'; '.join(ANALYSES)}.\n"
        f"- Controls: {', '.join(CONTROLS)}.\n"
        "- To point the researcher somewhere, name the page and the analysis exactly as above, "
        'for example "Analyses, Add analysis, Season dates". Never describe a button or feature '
        "not listed here. When they ask you to run or add one of these, you may propose it: "
        "they see a card to add it with one click."
    )
