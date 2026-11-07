"""What kind of question the researcher asked, decided by code before the model sees it.

A small model follows instructions better when it is given fewer of them. So each kind of
question gets only the rules, facts and tools it needs:

- data: about the researcher's own areas and results; the facts about the open workspace
  and the tool to read a series, no literature search
- research: about what published studies found; the literature search, no workspace facts
- method: about a method, an index or a setting; a short glossary from the catalogue and
  the settings Magonia accepts, no tools
- chat: a greeting or thanks; nothing but who Magonia is
- general: anything else, or a question of two kinds at once; everything, as before routing

When the signals disagree or are absent, the question is general: routing only ever takes
away what a question clearly does not need.
"""

import re
from typing import Literal

from engine.catalogue import CATALOGUE

Kind = Literal["data", "research", "method", "chat", "general"]

# What the researcher sees under the answer, saying where it came from
SOURCES: dict[str, str] = {
    "data": "Answered from your workspace",
    "research": "Answered from the literature",
    "method": "General knowledge and Magonia's catalogue",
    "chat": "",
    "general": "",
}

RESEARCH = re.compile(
    r"\b(papers?|stud(y|ies)|literature|published|publications?|evidence|cite|citations?|"
    r"references?|reviews?|what is known|state of the art|authors?|journals?|et al|"
    # how well a method or product works is a question the literature answers
    r"limits?|limitations?|drawbacks?|weakness(es)?|accuracy|reliab(le|ility)|known (issues|problems)|"
    r"how (well|accurate|reliable)|"
    # in French
    r"[ée]tudes?|recherches?|litt[ée]rature|articles?|que (disent|dit)|travaux)\b"
    r"|\(\d{4}\)",
    re.IGNORECASE,
)
DATA = re.compile(
    r"\b(my|our|this|these)\s+(areas?|orchards?|forests?|fields?|sites?|data|charts?|"
    r"series|results?|experiments?|workspace|analys[ie]s|cards?|board)\b"
    r"|\bthe (charts?|results?|experiments?|workspace|board|cards?)\b"
    r"|\bwhich (year|month|season)\b",
    re.IGNORECASE,
)
METHOD = re.compile(
    r"\b(what is|what's|what are|explain|meaning of|define|difference between|"
    r"hyperparameters?|settings?|which (model|index|indices|variable|method)s?|"
    r"should i (use|try|choose|pick))\b",
    re.IGNORECASE,
)
SETTING = re.compile(r"\b(hyperparameters?|settings?|parameters?)\b", re.IGNORECASE)
CHAT = re.compile(
    r"^\s*(hi|hello|hey|salam|bonjour|thanks?|thank you|merci|good (morning|evening|night)|"
    r"who are you|ok(ay)?|great|cool)\b",
    re.IGNORECASE,
)


# A short question that only makes sense after the one before: "And in Tunisia?", "What about
# forests?", "Same for 2023?"
FOLLOW_UP = re.compile(
    r"^\s*(and|what about|how about|same|also|but|then|in|for|or)\b.{0,60}$", re.IGNORECASE
)


FRENCH = re.compile(
    r"\b(le|la|les|des|est|et|une|du|pour|dans|que|qui|sur|avec|sont|quels?|quelles?|"
    r"comment|pourquoi|bonjour|merci|peux|tu|vous|je|mon|ma|mes)\b",
    re.IGNORECASE,
)


def in_french(question: str) -> bool:
    """Whether the question is written in French: enough of its words are French ones."""
    words = re.findall(r"[a-zà-ÿ']+", question.lower())
    return len(words) >= 2 and len(FRENCH.findall(question)) / len(words) >= 0.2


def follows(question: str) -> bool:
    return bool(FOLLOW_UP.match(question)) and len(question.split()) <= 10


NAMED = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]+\b")


def together(follow_up: str, earlier: str) -> str:
    """A follow-up and the question it follows, as one topic. When the follow-up names a place
    or a thing ("And in Tunisia?"), it replaces the one the earlier question named."""
    named = NAMED.findall(follow_up.strip()[1:] if follow_up.strip() else "")
    if named:
        first, *rest = earlier.split(" ", 1)
        earlier = first + " " + NAMED.sub("", rest[0]) if rest else earlier
    return f"{follow_up} {earlier}"


def route(question: str, areas: list[str] = (), has_view: bool = False) -> Kind:
    """The kind of a question; areas are the names of the researcher's open areas."""
    if CHAT.match(question) and len(question) <= 40:
        return "chat"
    named_area = any(a and a.lower() in question.lower() for a in areas)
    kinds = {
        kind
        for kind, matched in (
            ("research", RESEARCH.search(question)),
            ("data", has_view and (DATA.search(question) or named_area)),
            # a method question names something Magonia can explain
            (
                "method",
                METHOD.search(question) and (SETTING.search(question) or glossary(question)),
            ),
        )
        if matched
    }
    if kinds == {"research", "method"}:
        return "research"  # what studies found about a method is still a literature question
    if len(kinds) == 1:
        return kinds.pop()
    return "general"


MODELS = {
    "ridge": "Ridge: a linear regression whose weights are shrunk towards zero by alpha, so "
    "correlated predictors share the weight; fast, stable, and its weights explain it.",
    "random forest": "Random Forest: many decision trees, each on a resample of the years and "
    "a subset of predictors, averaged; n_estimators trees, max_depth deep, min_samples_leaf "
    "years per leaf, max_features the share of predictors tried at each split.",
    "xgboost": "XGBoost: trees added one after another, each correcting the errors of the "
    "previous ones; learning_rate shrinks each tree's step, subsample and colsample_bytree "
    "use a share of years and predictors per tree, min_child_weight stops tiny leaves.",
    "permutation importance": "Permutation importance: how much a model's error grows when "
    "one predictor's values are shuffled, breaking its link with the target.",
}


def glossary(question: str) -> str:
    """The catalogue's own explanation of the variables and models a question names."""
    text = question.lower()
    lines = []
    for v in CATALOGUE.values():
        names = {v.key.replace("_", " "), v.name.lower()}
        if v.learn and any(re.search(rf"\b{re.escape(n)}\b", text) for n in names):
            learn = v.learn
            lines.append(
                f"- {v.name} ({v.product}, {v.resolution}, {v.cadence}): {learn.what} "
                f"Formula: {learn.formula}. Reading: {learn.reading} Good for: "
                f"{'; '.join(learn.uses)}. Watch out: {' '.join(learn.limits)}"
            )
    lines += [f"- {line}" for name, line in MODELS.items() if name in text]
    if re.search(r"\b(variables|indices|indexes)\b", text) and not lines:
        lines = [f"- {v.name}: {v.learn.what}" for v in CATALOGUE.values() if v.learn]
    if not lines:
        return ""
    return "What Magonia's catalogue says (use it, in your own words):\n" + "\n".join(lines)
