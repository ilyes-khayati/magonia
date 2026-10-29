"""Analyses Magonia proposes (requirement AI-07).

When the researcher asks for an analysis, a forecast or another period, the model may call a
tool that describes it. Code checks the description against what the workspace has, and the
interface shows it as a card to add with one click. Nothing is run, added or changed until
the researcher clicks: the model can suggest, never act.
"""

import re

KINDS = {
    "correlation": "Correlation and lag",
    "decomposition": "Trend and season",
    "trend": "Long-term trend",
    "phenology": "Season dates",
    "lags": "Memory and lags",
    "experiment": "Forecast experiment",
}
VARIABLES = {"ndvi", "lst", "spei"}
MODELS = {
    "ridge": "Ridge",
    "randomforest": "RandomForest",
    "random forest": "RandomForest",
    "xgboost": "XGBoost",
}
MONTH = re.compile(r"^(\d{4})(?:-(\d{2}))?$")

PROPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_analysis",
        "description": (
            "Propose an analysis for the researcher to add with one click: nothing runs until "
            "they confirm. Use it when they ask for an analysis, a forecast or another period."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(KINDS)},
                "variable": {
                    "type": "string",
                    "description": "ndvi, lst or spei: the one studied or forecast",
                },
                "driver": {
                    "type": "string",
                    "description": "for a correlation: the other variable",
                },
                "drivers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "for lags or an experiment",
                },
                "area": {"type": "string", "description": "area name, for lags or an experiment"},
                "start": {
                    "type": "string",
                    "description": "first month of the period, YYYY or YYYY-MM, if asked",
                },
                "end": {
                    "type": "string",
                    "description": "last month of the period, YYYY or YYYY-MM, if asked",
                },
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "for an experiment",
                },
                "test_years": {
                    "type": "integer",
                    "description": "for an experiment: years held out",
                },
                "why": {"type": "string", "description": "one sentence: what it will show"},
            },
            "required": ["kind", "why"],
        },
    },
}


class ProposalError(ValueError):
    """A proposal that does not fit the workspace; the message goes back to the model."""


def month(text: str, end: bool) -> str:
    m = MONTH.match(text.strip())
    if not m:
        raise ProposalError(f"the period must be written YYYY or YYYY-MM, not {text!r}")
    return f"{m[1]}-{m[2] or ('12' if end else '01')}"


def proposal(arguments: dict, areas: list[str]) -> dict:
    """The proposal, checked and in the interface's terms."""
    kind = str(arguments.get("kind", "")).lower()
    if kind not in KINDS:
        raise ProposalError(f"kind must be one of {', '.join(KINDS)}")
    out: dict = {"kind": kind, "label": KINDS[kind], "why": str(arguments.get("why", "")).strip()}

    def variable(name: str, value) -> str:
        v = str(value or "").lower()
        if v not in VARIABLES:
            raise ProposalError(f"{name} must be ndvi, lst or spei")
        return v

    if kind in ("correlation", "decomposition", "trend", "lags", "experiment"):
        out["variable"] = variable("variable", arguments.get("variable") or "ndvi")
    if kind == "phenology":
        out["variable"] = "ndvi"
    if kind == "correlation":
        out["driver"] = variable("driver", arguments.get("driver"))
    if kind in ("lags", "experiment"):
        drivers = arguments.get("drivers") or [v for v in ("lst", "spei") if v != out["variable"]]
        out["drivers"] = [
            variable("a driver", d) for d in drivers if str(d).lower() != out["variable"]
        ]
    if area := str(arguments.get("area") or "").strip():
        found = [a for a in areas if a.lower() == area.lower()]
        if not found:
            raise ProposalError(f"no area is called {area!r}; the areas are {', '.join(areas)}")
        out["area"] = found[0]
    if kind == "experiment":
        names = [MODELS.get(str(m).lower()) for m in arguments.get("models") or []]
        if any(n is None for n in names):
            raise ProposalError("models must be Ridge, Random Forest or XGBoost")
        out["models"] = [n for n in ("Ridge", "RandomForest", "XGBoost") if n in names] or [
            "Ridge",
            "RandomForest",
            "XGBoost",
        ]
        years = arguments.get("test_years")
        out["test_years"] = min(max(int(years), 1), 10) if str(years or "").isdigit() else 3
    start, end = arguments.get("start"), arguments.get("end")
    if start or end:
        out["period"] = {
            "start": month(str(start), False) if start else None,
            "end": month(str(end), True) if end else None,
        }
    return out


def describe(p: dict) -> str:
    """The proposal in one line, as the researcher will see it on the button."""
    words = {"ndvi": "NDVI", "lst": "LST", "spei": "SPEI"}
    what = p["label"]
    if p["kind"] == "correlation":
        what += f": {words[p['variable']]} and {words[p['driver']]}"
    elif "variable" in p:
        what += f": {words[p['variable']]}"
    if p.get("drivers"):
        what += f" with {', '.join(words[d] for d in p['drivers'])}"
    if p.get("area"):
        what += f", {p['area']}"
    if period := p.get("period"):
        what += f", period {period['start'] or '…'} to {period['end'] or '…'}"
    return what
