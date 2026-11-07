import type { Models } from "./analyses";
import type { Area, ModelsBody, SeriesOptions, VariableKey } from "./api";

// Forecasting experiments on the Model page. Each is a recipe the researcher edits and the
// recipe it last ran: results always belong to a run, so nothing refits while editing.

export type ModelName = "Ridge" | "RandomForest" | "XGBoost" | "MLP" | "LSTM" | "GRU" | "TCN";
export const MODEL_NAMES: ModelName[] = ["Ridge", "RandomForest", "XGBoost", "MLP", "LSTM", "GRU", "TCN"];
// the paper's three, chosen for a new experiment; the networks are added by choice
export const DEFAULT_MODELS: ModelName[] = ["Ridge", "RandomForest", "XGBoost"];
export const DEEP: ModelName[] = ["MLP", "LSTM", "GRU", "TCN"];
// One line on what each model is, under its name in the recipe
export const MODEL_KIND: Record<ModelName, string> = {
  Ridge: "Linear regression with an L2 penalty",
  RandomForest: "Bagged decision trees",
  XGBoost: "Gradient-boosted trees",
  MLP: "Feed-forward network over the lag window",
  LSTM: "Recurrent network over the lag sequence",
  GRU: "Recurrent network, lighter than the LSTM",
  TCN: "Dilated convolutions over the lag sequence",
};
export const MODEL_LABEL: Record<ModelName, string> = {
  Ridge: "Ridge",
  RandomForest: "Random Forest",
  XGBoost: "XGBoost",
  MLP: "MLP",
  LSTM: "LSTM",
  GRU: "GRU",
  TCN: "TCN",
};

const NEURAL: Setting[] = [
  { key: "hidden", label: "Hidden units", min: 4, max: 256, step: 4, fallback: "32" },
  { key: "lr", label: "Learning rate", min: 0.0001, max: 0.1, step: 0.0005, fallback: "0.005" },
  { key: "weight_decay", label: "Weight decay (L2)", min: 0, max: 0.1, step: 0.0001, fallback: "0.0001" },
  { key: "epochs", label: "Maximum epochs", min: 50, max: 5000, step: 50, fallback: "500, early stopping" },
];

// Hyperparameters that can be set by hand instead of searched, with the engine's limits
// (engine/models.py) and the value used when left empty (the library's default)
export type Setting = { key: string; label: string; min: number; max: number; step: number; fallback: string };
export const SETTABLE: Record<ModelName, Setting[]> = {
  Ridge: [{ key: "alpha", label: "Alpha (L2 penalty)", min: 1e-6, max: 1e6, step: 0.1, fallback: "1.0" }],
  RandomForest: [
    { key: "n_estimators", label: "Number of trees (n_estimators)", min: 10, max: 2000, step: 10, fallback: "100" },
    { key: "max_depth", label: "Maximum depth (max_depth)", min: 1, max: 50, step: 1, fallback: "none" },
    { key: "min_samples_leaf", label: "Minimum samples per leaf", min: 1, max: 50, step: 1, fallback: "1" },
    { key: "max_features", label: "Features per split (max_features)", min: 0.05, max: 1, step: 0.05, fallback: "1.0" },
  ],
  XGBoost: [
    { key: "n_estimators", label: "Boosting rounds (n_estimators)", min: 10, max: 3000, step: 10, fallback: "100" },
    { key: "max_depth", label: "Maximum depth (max_depth)", min: 1, max: 15, step: 1, fallback: "6" },
    { key: "learning_rate", label: "Learning rate (eta)", min: 0.001, max: 1, step: 0.01, fallback: "0.3" },
    { key: "subsample", label: "Row subsample", min: 0.1, max: 1, step: 0.05, fallback: "1.0" },
    { key: "colsample_bytree", label: "Column subsample per tree", min: 0.1, max: 1, step: 0.05, fallback: "1.0" },
    { key: "min_child_weight", label: "Minimum child weight", min: 0, max: 50, step: 1, fallback: "1" },
  ],
  MLP: NEURAL,
  LSTM: NEURAL,
  GRU: NEURAL,
  TCN: NEURAL,
};

export type Recipe = {
  area: number | null;
  response: VariableKey;
  drivers: VariableKey[];
  own_lags: number[] | null; // null: recommended by code
  driver_lags: Partial<Record<VariableKey, number[]>> | null;
  test_years: number;
  models: ModelName[];
  params: Partial<Record<ModelName, Record<string, number>>>; // a model left out is tuned
  calendar: boolean;
  rolling: boolean; // also test on earlier windows
};

export type Experiment = {
  id: number;
  name: string;
  recipe: Recipe;
  ran: Recipe | null;
  explain: boolean; // explanations asked for, for the run
  stability?: boolean; // the explanations checked across training windows, for the run
};

// A new experiment chooses nothing for the researcher beyond what to forecast: the models and
// the predictors are theirs to pick. Its own past is left to the memory test until they type
// lags.
export const EMPTY: Omit<Recipe, "area"> = {
  response: "ndvi",
  drivers: [],
  own_lags: null,
  driver_lags: null,
  test_years: 3,
  models: [],
  params: {},
  calendar: false,
  rolling: true,
};

// Equal recipes compare equal whatever the order of their choices
function normal(r: Recipe): Recipe {
  return {
    ...r,
    drivers: [...r.drivers].sort(),
    models: MODEL_NAMES.filter((m) => r.models.includes(m)),
    params: Object.fromEntries(Object.entries(r.params).filter(([m, p]) => r.models.includes(m as ModelName) && p)),
  };
}

export const sameRecipe = (a: Recipe | null, b: Recipe | null) =>
  a !== null && b !== null && JSON.stringify(normal(a)) === JSON.stringify(normal(b));

export function newExperiment(list: Experiment[], area: number | null, from?: Recipe): Experiment {
  const id = Math.max(0, ...list.map((e) => e.id)) + 1;
  const recipe = from ? structuredClone(from) : { ...structuredClone(EMPTY), area };
  return { id, name: `Experiment ${id}`, recipe, ran: null, explain: false };
}

// The request a run makes; later choices are sent only when they differ from the defaults
export function bodyOf(r: Recipe, options: (areaId: number, variable: VariableKey) => SeriesOptions): ModelsBody {
  const body: ModelsBody = {
    response: options(r.area!, r.response),
    drivers: r.drivers.map((k) => options(r.area!, k)),
    own_lags: r.own_lags,
    driver_lags: r.driver_lags,
    test_years: r.test_years,
  };
  const models = MODEL_NAMES.filter((m) => r.models.includes(m));
  // the API fits the paper's three when told nothing, so only another choice is sent
  if (models.join() !== DEFAULT_MODELS.join()) body.models = models;
  const params = Object.fromEntries(models.filter((m) => r.params[m]).map((m) => [m, r.params[m]!]));
  if (Object.keys(params).length) body.params = params;
  if (!r.calendar) body.calendar = false;
  if (!r.rolling) body.rolling = false;
  return body;
}

// One line saying what an experiment does, for the list
export function recipeLine(r: Recipe, title: (key: VariableKey) => string): string {
  const models = MODEL_NAMES.filter((m) => r.models.includes(m)).map((m) => MODEL_LABEL[m]);
  return [
    title(r.response),
    models.join(", "),
    r.drivers.length ? `with ${r.drivers.map(title).join(", ")}` : "no drivers",
    `last ${r.test_years} ${r.test_years === 1 ? "year" : "years"} held out`,
  ].join(" · ");
}

const isRecipe = (r: unknown): r is Recipe =>
  typeof r === "object" && r !== null && typeof (r as Recipe).response === "string" && Array.isArray((r as Recipe).models);

// Saved experiments, and forecast cards from before the Model page, which become experiments
export function readExperiments(saved: unknown, oldCards: Models[] = []): Experiment[] {
  const list = Array.isArray(saved)
    ? saved.filter((e): e is Experiment => typeof e === "object" && e !== null && typeof e.id === "number" && isRecipe(e.recipe))
    : [];
  for (const card of oldCards) {
    // a forecast card fitted all three models with the calendar and earlier windows
    const recipe: Recipe = {
      ...EMPTY,
      models: ["Ridge", "RandomForest", "XGBoost"],
      calendar: true,
      area: null,
      response: card.response,
      drivers: card.drivers,
      own_lags: card.own_lags,
      driver_lags: card.driver_lags,
      test_years: card.test_years,
    };
    const e = newExperiment(list, null, recipe);
    list.push({ ...e, name: `Forecast ${e.id}`, ran: recipe });
  }
  return list;
}

// What differs between two recipes, in words, said before two runs are compared
export function recipeDifferences(a: Recipe, b: Recipe, areas: Area[], name: (key: VariableKey) => string): string[] {
  const out: string[] = [];
  const area = (id: number | null) => areas.find((x) => x.id === id)?.name ?? "no area";
  const list = (xs: string[]) => (xs.length ? xs.join(", ") : "none");
  const lags = (l: number[] | null) => (l ? l.join(", ") : "chosen by the test");
  if (a.area !== b.area) out.push(`area ${area(a.area)} against ${area(b.area)}`);
  if (a.response !== b.response) out.push(`forecast ${name(a.response)} against ${name(b.response)}`);
  if (JSON.stringify([...a.drivers].sort()) !== JSON.stringify([...b.drivers].sort()))
    out.push(`drivers ${list(a.drivers.map(name))} against ${list(b.drivers.map(name))}`);
  if (JSON.stringify(a.own_lags) !== JSON.stringify(b.own_lags)) out.push(`own lags ${lags(a.own_lags)} against ${lags(b.own_lags)}`);
  if (a.calendar !== b.calendar) out.push(a.calendar ? "calendar only in the first" : "calendar only in the second");
  if (a.test_years !== b.test_years) out.push(`last ${a.test_years} against ${b.test_years} years held out`);
  if (JSON.stringify([...a.models].sort()) !== JSON.stringify([...b.models].sort()))
    out.push(`models ${list(a.models.map((m) => MODEL_LABEL[m]))} against ${list(b.models.map((m) => MODEL_LABEL[m]))}`);
  if (JSON.stringify(a.params) !== JSON.stringify(b.params)) out.push("settings set by hand differ");
  if (a.rolling !== b.rolling) out.push(a.rolling ? "earlier windows only in the first" : "earlier windows only in the second");
  return out;
}
