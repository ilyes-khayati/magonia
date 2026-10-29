import type { Models } from "./analyses";
import type { Area, ModelsBody, SeriesOptions, VariableKey } from "./api";

// Forecasting experiments on the Model page. Each is a recipe the researcher edits and the
// recipe it last ran: results always belong to a run, so nothing refits while editing.

export type ModelName = "Ridge" | "RandomForest" | "XGBoost";
export const MODEL_NAMES: ModelName[] = ["Ridge", "RandomForest", "XGBoost"];
export const MODEL_LABEL: Record<ModelName, string> = {
  Ridge: "Ridge",
  RandomForest: "Random Forest",
  XGBoost: "XGBoost",
};

// What can be set by hand instead of tuned, with the engine's limits (engine/models.py)
export type Setting = { key: string; label: string; min: number; max: number; step: number };
export const SETTABLE: Record<ModelName, Setting[]> = {
  Ridge: [{ key: "alpha", label: "Alpha (shrinkage)", min: 1e-6, max: 1e6, step: 0.1 }],
  RandomForest: [
    { key: "n_estimators", label: "Trees", min: 10, max: 2000, step: 10 },
    { key: "max_depth", label: "Maximum depth", min: 1, max: 50, step: 1 },
    { key: "min_samples_leaf", label: "Smallest leaf", min: 1, max: 50, step: 1 },
    { key: "max_features", label: "Share of inputs per split", min: 0.05, max: 1, step: 0.05 },
  ],
  XGBoost: [
    { key: "n_estimators", label: "Trees", min: 10, max: 3000, step: 10 },
    { key: "max_depth", label: "Maximum depth", min: 1, max: 15, step: 1 },
    { key: "learning_rate", label: "Learning rate", min: 0.001, max: 1, step: 0.01 },
    { key: "subsample", label: "Share of months per tree", min: 0.1, max: 1, step: 0.05 },
    { key: "colsample_bytree", label: "Share of inputs per tree", min: 0.1, max: 1, step: 0.05 },
    { key: "min_child_weight", label: "Smallest leaf weight", min: 0, max: 50, step: 1 },
  ],
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

// The paper's method: the three models tuned on the training years, lags chosen by the tests,
// the calendar, the last three years held out and earlier windows as well
export const PAPER: Omit<Recipe, "area"> = {
  response: "ndvi",
  drivers: ["lst", "spei"],
  own_lags: null,
  driver_lags: null,
  test_years: 3,
  models: [...MODEL_NAMES],
  params: {},
  calendar: true,
  rolling: true,
};

// The area is not part of the method
export const isPaper = (r: Recipe) => sameRecipe({ ...r, area: null }, { ...PAPER, area: null });

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
  const recipe = from ? structuredClone(from) : { ...structuredClone(PAPER), area };
  return { id, name: from ? `Experiment ${id}` : `Paper method ${id}`, recipe, ran: null, explain: false };
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
  if (models.length < MODEL_NAMES.length) body.models = models;
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
    const recipe: Recipe = {
      ...PAPER,
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
