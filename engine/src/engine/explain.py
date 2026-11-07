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

from dataclasses import asdict, dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import weightedtau
from sklearn.inspection import permutation_importance
from sklearn.model_selection import TimeSeriesSplit
from xgboost import DMatrix

from engine.models import LABELS as MODEL_LABELS
from engine.models import estimator

CV = TimeSeriesSplit(n_splits=5)
ORDER = (
    "XGBoost",
    "RandomForest",
    "Ridge",
    "MLP",
    "LSTM",
    "GRU",
    "TCN",
)  # the paper's, then networks


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
    # how far each family's share moves from seed to seed: model -> family -> [low, high]
    family_range: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    # error rise when a family is left out and the model refitted: model -> family -> share
    dropped: dict[str, dict[str, float]] = field(default_factory=dict)
    # the model's own explanation (coefficients, TreeSHAP, impurity, gradient × input):
    # model -> {"method", "importance": feature -> value, "tau": agreement with shuffling}
    native: dict[str, dict] = field(default_factory=dict)
    # month by month, how far each family moves the forecast when replaced by its mean:
    # model -> list of {"date", family -> change}
    timeline: dict[str, list[dict]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "importance": self.importance,
            "families": self.families,
            "agreement": [p.to_dict() for p in self.agreement],
            "seeds": self.seeds,
            "family_range": self.family_range,
            "dropped": self.dropped,
            "native": self.native,
            "timeline": self.timeline,
        }


def drop_family(name: str, params: dict, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """Drop-column importance by family (XAI-02): how much the out-of-fold error rises when a
    family's inputs are left out and the model is refitted without them. Unlike shuffling, it
    asks whether the model needs the family at all, or can do as well with what is left."""

    def oof_rmse(columns: list[str]) -> float:
        errors = []
        for fit, val in CV.split(X):
            model = estimator(name, params).fit(X.iloc[fit][columns], y.iloc[fit])
            errors.append(np.mean((y.iloc[val] - model.predict(X.iloc[val][columns])) ** 2))
        return float(np.sqrt(np.mean(errors)))

    every = list(X.columns)
    base = oof_rmse(every)
    out = {}
    for fam in dict.fromkeys(family(c) for c in every):
        rest = [c for c in every if family(c) != fam]
        if rest:
            out[fam] = (oof_rmse(rest) - base) / base
    return out


NATIVE = {
    "Ridge": "standardised coefficients",
    "XGBoost": "TreeSHAP",
    "RandomForest": "impurity decrease",
}


def native(name: str, model, X: pd.DataFrame) -> tuple[str, pd.Series]:
    """Each model's own account of its inputs, in its own terms: what a researcher would get
    from the library without Magonia. Mean absolute size per input."""
    if name == "Ridge":
        ridge = model[-1]
        return NATIVE[name], pd.Series(np.abs(ridge.coef_), index=X.columns)
    if name == "XGBoost":
        contributions = model.get_booster().predict(DMatrix(X), pred_contribs=True)[:, :-1]
        return NATIVE[name], pd.Series(np.abs(contributions).mean(axis=0), index=X.columns)
    if name == "RandomForest":
        return NATIVE[name], pd.Series(model.feature_importances_, index=X.columns)
    return "gradient × input", pd.Series(np.abs(model.gradients(X)).mean(axis=0), index=X.columns)


def timeline(model, X: pd.DataFrame) -> list[dict]:
    """For every month, how much the forecast moves when one family of inputs is set to its
    average: positive when that family pushed the forecast up that month."""
    families = pd.Series({c: family(c) for c in X.columns})
    full = model.predict(X)
    out = pd.DataFrame(index=X.index)
    for name, columns in families.groupby(families).groups.items():
        if name == "noise probe":
            continue
        flat = X.copy()
        flat[list(columns)] = X[list(columns)].mean().to_numpy()
        out[name] = full - model.predict(flat)
    return [
        {"date": f"{d:%Y-%m}", **{k: round(float(v), 5) for k, v in row.items()}}
        for d, row in out.iterrows()
    ]


def explain(X: pd.DataFrame, y: pd.Series, params: dict[str, dict], seeds: int = 5) -> Explanation:
    """Permutation importance, family shares and agreement of the three models, on the
    training years only. Ridge fits the same every time, but its shuffles vary by seed."""
    runs, families, ranges, dropped = {}, {}, {}, {}
    for name in [n for n in ORDER if n in params]:
        runs[name] = [oof_permutation(name, params[name], X, y, s) for s in range(seeds)]
        fam = [oof_family(name, params[name], X, y, s) for s in range(seeds)]
        families[name] = shares(pd.concat(fam, axis=1).mean(axis=1))
        each = pd.concat([shares(f) for f in fam], axis=1)
        ranges[name] = {k: [float(each.loc[k].min()), float(each.loc[k].max())] for k in each.index}
        dropped[name] = drop_family(name, params[name], X, y)
    importance = {m: pd.concat(r, axis=1).mean(axis=1).to_dict() for m, r in runs.items()}
    own, months = {}, {}
    for name in runs:
        model = estimator(name, params[name]).fit(X, y)
        method, values = native(name, model, X)
        shuffled = pd.Series(importance[name])
        own[name] = {
            "method": method,
            "importance": values.to_dict(),
            "tau": tau(shuffled.clip(lower=0), values),
        }
        months[name] = timeline(model, X)
    return Explanation(
        importance,
        {m: f.to_dict() for m, f in families.items()},
        agreement(runs),
        seeds,
        ranges,
        dropped,
        own,
        months,
    )


LABELS = MODEL_LABELS


def describe(area: str, explained: Explanation) -> list[str]:
    """What each model leans on, by input and by family, and whether the models agree."""
    lines = []
    for name in [n for n in ORDER if n in explained.importance]:
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
    # the comparisons are written here, so the assistant does not have to rank numbers itself;
    # they come first, before each model's details
    details, lines = lines, []
    names = [n for n in ORDER if n in explained.families]
    if len(names) > 1:
        for fam in ("own history", "LST", "drought", "calendar"):
            share = {n: explained.families[n].get(fam, 0.0) for n in names}
            if max(share.values()) < 0.10:
                continue
            most, least = max(share, key=share.get), min(share, key=share.get)
            lines.append(
                f"{area}: of the models, {LABELS[most]} leans most on {fam} "
                f"({100 * share[most]:.0f}%) and {LABELS[least]} least ({100 * share[least]:.0f}%)."
            )
    for pair in explained.agreement:
        if pair.separable is None or len(explained.importance) < 2:
            continue
        m1, m2 = (LABELS[m] for m in pair.pair.split(" vs "))
        itself = min(p.tau_lo for p in explained.agreement if p.separable is None)
        moved = f"{100 * pair.dist:.0f}% of the importance would have to move"
        if pair.separable:
            line = (
                f"{m1} and {m2} explain the data differently: their rankings agree less (weighted "
                f"τ {pair.tau:.2f}) than either model agrees with itself refitted with another "
                f"seed (at least {itself:.2f}), and {moved}."
            )
        else:
            line = (
                f"{m1} and {m2} agree within what refitting with another seed changes: their "
                f"rankings (weighted τ {pair.tau:.2f}) are as close as a model is to itself "
                f"(at least {itself:.2f}); {moved}."
            )
        lines.append(f"{area}: {line}")
    for name in [n for n in ORDER if n in explained.dropped]:
        need = {k: v for k, v in explained.dropped[name].items() if k != "noise probe"}
        if not need:
            continue
        ranked = sorted(need.items(), key=lambda kv: -kv[1])
        details.append(
            f"{area}: refitted without a family, {LABELS[name]}'s error "
            + ", ".join(
                f"{'rises' if v > 0 else 'falls'} by {abs(100 * v):.0f}% without {k}"
                for k, v in ranked
            )
            + "."
        )
    for name in [n for n in ORDER if n in explained.native]:
        own = explained.native[name]
        verdict = (
            "agrees with shuffling"
            if own["tau"] >= 0.7
            else "partly agrees with shuffling"
            if own["tau"] >= 0.4
            else "disagrees with shuffling"
        )
        details.append(
            f"{area}: {LABELS[name]}'s own explanation ({own['method']}) {verdict} on which "
            f"inputs matter (weighted τ {own['tau']:.2f})."
        )
    for name in [n for n in ORDER if n in explained.timeline]:
        months = pd.DataFrame(explained.timeline[name]).set_index("date")
        if months.empty:
            continue
        size = months.abs()
        top = size.max().idxmax()
        when = size[top].idxmax()
        details.append(
            f"{area}: month by month, {LABELS[name]}'s forecast is moved most by {top}, most of "
            f"all in {when} ({months.loc[when, top]:+.3f})."
        )
    return lines + details


@dataclass
class Stability:
    """What each model leans on when its training years end earlier."""

    windows: list[dict]  # train_end, each model's share by family, and its settings
    leading: dict[str, list[str]]  # model -> the family it leans on most, window by window
    summary: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def stability(
    area: str,
    X: pd.DataFrame,
    y: pd.Series,
    params: dict[str, dict],
    test_start: str,
    windows: int = 4,
    seeds: int = 3,
    min_train_years: int = 8,
    retune: bool = True,
    draws: int = 12,
) -> Stability:
    """Explain the models again on training years that end 0, 1, 2… years before the test,
    and say which models keep the same story. Seed noise is one null for an explanation; the
    years it was trained on are another, which the paper's comparison does not include. With
    retune, each window is tuned again as a researcher would, so a story that changes with
    the settings tuning picks shows up too."""
    from engine.models import tune

    found = []
    for back in range(windows):
        end = pd.Timestamp(test_start) - pd.DateOffset(years=back)
        train = X.index < end
        if train.sum() < 12 * min_train_years:
            break
        names = [n for n in ORDER if n in params]
        used = {
            n: tune(n, X[train], y[train], draws) if retune and back else params[n] for n in names
        }
        fam = {
            n: shares(
                pd.concat(
                    [oof_family(n, used[n], X[train], y[train], s) for s in range(seeds)],
                    axis=1,
                ).mean(axis=1)
            ).to_dict()
            for n in names
        }
        last = X.index[train][-1]
        found.append({"train_end": f"{last:%Y-%m}", "families": fam, "params": used})
    found.reverse()  # oldest first
    names = [n for n in ORDER if n in params]
    leading = {n: [max(w["families"][n], key=w["families"][n].get) for w in found] for n in names}
    summary = []
    if len(found) < 2:
        summary.append(
            f"{area}: too few years to train on in earlier windows; stability cannot be checked."
        )
    else:
        span = (
            f"{len(found)} training windows ending {found[0]['train_end']} to "
            f"{found[-1]['train_end']}" + (", each tuned again" if retune else "")
        )
        for n in names:
            kinds = list(dict.fromkeys(leading[n]))
            if len(kinds) == 1:
                share = [100 * w["families"][n][kinds[0]] for w in found]
                summary.append(
                    f"{area}: across {span}, {LABELS[n]} always leans most on {kinds[0]} "
                    f"({min(share):.0f}–{max(share):.0f}%)."
                )
            else:
                counts = ", ".join(f"{k} in {leading[n].count(k)}" for k in kinds)
                summary.append(
                    f"{area}: across {span}, {LABELS[n]} changes what it leans on most: {counts}; "
                    "its explanation depends on the years it was trained on."
                )
    return Stability(found, leading, summary)
