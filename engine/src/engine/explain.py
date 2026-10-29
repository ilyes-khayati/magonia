"""How each model explains the same inputs, and whether the models agree.

The method of the 2026 paper (notebook 05). Permutation importance is the same procedure for
every model class, so it is the one compared across models: the increase in squared error
when one input is shuffled, computed out of fold on a time-series split of the training
years and averaged over seeds. Inputs are also shuffled by family (own history, LST,
drought, calendar), so correlated lags cannot cover for one another. Two models agree when
their rankings and allocations are as close as one model refitted with another seed is to
itself; when the whole range between them lies outside both of those, the models explain the
data differently, beyond refitting noise.
"""

from dataclasses import asdict, dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import weightedtau
from sklearn.inspection import permutation_importance
from sklearn.model_selection import TimeSeriesSplit

from engine.models import estimator

CV = TimeSeriesSplit(n_splits=5)
ORDER = ("XGBoost", "RandomForest", "Ridge")  # as the paper lists them


def family(feature: str) -> str:
    if feature == "noise_probe":
        return "noise probe"
    if feature.startswith(("LST", "Land surface")):
        return "LST"
    if feature.startswith("SPEI"):
        return "drought"
    if feature.startswith("month"):
        return "calendar"
    return "own history"


def oof_permutation(name: str, params: dict, X: pd.DataFrame, y: pd.Series, seed: int) -> pd.Series:
    """Increase in MSE when each input is shuffled, averaged over ten shuffles and the folds."""
    folds = []
    for fit, val in CV.split(X):
        model = estimator(name, params, seed).fit(X.iloc[fit], y.iloc[fit])
        r = permutation_importance(
            model,
            X.iloc[val],
            y.iloc[val],
            n_repeats=10,
            random_state=seed,
            scoring="neg_mean_squared_error",
        )
        folds.append(r.importances_mean)
    return pd.Series(np.mean(folds, axis=0), index=X.columns)


def family_permutation(model, X: pd.DataFrame, y: pd.Series, rng, repeats: int = 10) -> pd.Series:
    """Increase in MSE when a whole family is shuffled with one row order."""
    families = pd.Series({c: family(c) for c in X.columns})
    base = np.mean((y - model.predict(X)) ** 2)
    out = {}
    for name, columns in families.groupby(families).groups.items():
        columns, increase = list(columns), []
        for _ in range(repeats):
            shuffled = X.copy()
            shuffled[columns] = X[columns].to_numpy()[rng.permutation(len(X))]
            increase.append(np.mean((y - model.predict(shuffled)) ** 2) - base)
        out[name] = np.mean(increase)
    return pd.Series(out)


def oof_family(name: str, params: dict, X: pd.DataFrame, y: pd.Series, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    folds = [
        family_permutation(
            estimator(name, params, seed).fit(X.iloc[fit], y.iloc[fit]),
            X.iloc[val],
            y.iloc[val],
            rng,
        )
        for fit, val in CV.split(X)
    ]
    return pd.concat(folds, axis=1).mean(axis=1)


def shares(s: pd.Series) -> pd.Series:
    s = s.clip(lower=0)
    return s / s.sum()


def tau(a: pd.Series, b: pd.Series) -> float:
    """Weighted Kendall's τ (Vigna, 2015): rank agreement weighted to the top of both."""
    return float(weightedtau(a.to_numpy(), b.to_numpy()).statistic)


def allocation(a: pd.Series, b: pd.Series) -> float:
    """Share of importance that would have to move to turn one allocation into the other."""
    return float(0.5 * np.abs(shares(a) - shares(b)).sum())


@dataclass
class Pair:
    pair: str
    tau: float
    tau_lo: float
    tau_hi: float
    dist: float
    dist_lo: float
    dist_hi: float
    separable: bool | None = None  # only for two different models

    def to_dict(self) -> dict:
        return asdict(self)


def agreement(runs: dict[str, list[pd.Series]]) -> list[Pair]:
    """Each model against itself over seeds, then every pair of models."""
    pairs, within = [], {}
    for m, series in runs.items():
        couples = list(combinations(series, 2))
        t, a = [tau(x, y) for x, y in couples], [allocation(x, y) for x, y in couples]
        within[m] = (min(t), max(a))
        pairs.append(
            Pair(f"{m} vs itself", np.median(t), min(t), max(t), np.median(a), min(a), max(a))
        )
    for m1, m2 in combinations(runs, 2):
        couples = [(x, y) for x in runs[m1] for y in runs[m2]]
        t, a = [tau(x, y) for x, y in couples], [allocation(x, y) for x, y in couples]
        separable = max(t) < min(within[m1][0], within[m2][0]) and min(a) > max(
            within[m1][1], within[m2][1]
        )
        pairs.append(
            Pair(
                f"{m1} vs {m2}",
                np.median(t),
                min(t),
                max(t),
                np.median(a),
                min(a),
                max(a),
                bool(separable),
            )
        )
    return pairs


@dataclass
class Explanation:
    importance: dict[str, dict[str, float]]  # model → feature → mean increase in MSE
    families: dict[str, dict[str, float]]  # model → family → share of importance
    agreement: list[Pair]
    seeds: int

    def to_dict(self) -> dict:
        return {
            "importance": self.importance,
            "families": self.families,
            "agreement": [p.to_dict() for p in self.agreement],
            "seeds": self.seeds,
        }


def explain(X: pd.DataFrame, y: pd.Series, params: dict[str, dict], seeds: int = 5) -> Explanation:
    """Permutation importance, family shares and agreement of the three models, on the
    training years only. Ridge fits the same every time, but its shuffles vary by seed."""
    runs, families = {}, {}
    for name in ORDER:
        runs[name] = [oof_permutation(name, params[name], X, y, s) for s in range(seeds)]
        fam = [oof_family(name, params[name], X, y, s) for s in range(seeds)]
        families[name] = shares(pd.concat(fam, axis=1).mean(axis=1))
    importance = {m: pd.concat(r, axis=1).mean(axis=1).to_dict() for m, r in runs.items()}
    return Explanation(
        importance,
        {m: f.to_dict() for m, f in families.items()},
        agreement(runs),
        seeds,
    )


LABELS = {"Ridge": "Ridge", "RandomForest": "Random Forest", "XGBoost": "XGBoost"}


def describe(area: str, explained: Explanation) -> list[str]:
    """What each model leans on, by input and by family, and whether the models agree."""
    lines = []
    for name in ORDER:
        top = shares(pd.Series(explained.importance[name])).sort_values(ascending=False)[:3]
        fam = pd.Series(explained.families[name]).sort_values(ascending=False)
        fam = fam[fam >= 0.05]
        lines.append(
            f"{area}: {LABELS[name]} leans most on "
            + ", ".join(f"{f.replace('_', ' ')} ({100 * v:.0f}%)" for f, v in top.items())
            + "; by family "
            + ", ".join(f"{f} {100 * v:.0f}%" for f, v in fam.items())
            + "."
        )
    for pair in explained.agreement:
        if pair.separable is None:
            continue
        m1, m2 = (LABELS[m] for m in pair.pair.split(" vs "))
        itself = min(p.tau_lo for p in explained.agreement if p.separable is None)
        if pair.separable:
            verdict = (
                "explain the data differently, beyond what refitting with another seed changes"
            )
        else:
            verdict = "agree within what refitting with another seed changes"
        lines.append(
            f"{area}: {m1} and {m2} {verdict} (weighted τ {pair.tau:.2f}, against at least "
            f"{itself:.2f} for a model with itself; {100 * pair.dist:.0f}% of the importance "
            "would have to move)."
        )
    return lines
