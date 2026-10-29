import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Area, SeriesOptions, Variable, VariableKey } from "../api";
import {
  bodyOf,
  newExperiment,
  recipeDifferences,
  recipeLine,
  sameRecipe,
  type Experiment,
  type Recipe as RecipeT,
} from "../experiments";
import type { Entry } from "./ChartCard";
import { CloseIcon, PlusIcon } from "./Icons";
import Recipe from "./Recipe";
import { useRun } from "../useRun";
import Results from "./Results";

type Props = {
  experiments: Experiment[];
  onChange: (experiments: Experiment[]) => void;
  areas: Area[];
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean; // seasonal means cannot be forecast month by month
  dataPath: string | null;
  mapPath: string | null;
  onShown: (ids: number[]) => void; // the experiments on screen, which Magonia is told about
};

// Forecasting experiments, kept like the runs of a notebook: each has its recipe and its
// results, and two can be put side by side
export default function ModelPage(props: Props) {
  const { experiments, onChange, areas, variables, title, entries, options, seasonal, dataPath, mapPath, onShown } = props;
  const [openId, setOpenId] = useState<number | null>(null);
  const [comparing, setComparing] = useState<number[]>([]);
  const open = experiments.find((e) => e.id === openId) ?? experiments[0] ?? null;
  const shown = comparing.length === 2 ? comparing.join(",") : String(open?.id ?? "");
  useEffect(() => onShown(shown ? shown.split(",").map(Number) : []), [shown, onShown]);
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  // an experiment from before areas were chosen per experiment runs on the first area
  const firstArea = areas[0]?.id ?? null;
  const resolve = (r: RecipeT | null): RecipeT | null =>
    r && (r.area !== null && areas.some((a) => a.id === r.area) ? r : firstArea === null ? null : { ...r, area: firstArea });

  const update = (id: number, change: Partial<Experiment>) =>
    onChange(experiments.map((e) => (e.id === id ? { ...e, ...change } : e)));
  const add = (from?: RecipeT, name?: string) => {
    const e = newExperiment(experiments, firstArea, from);
    onChange([...experiments, name ? { ...e, name } : e]);
    setOpenId(e.id);
    setComparing([]);
  };
  const remove = (id: number) => {
    onChange(experiments.filter((e) => e.id !== id));
    setComparing(comparing.filter((c) => c !== id));
    if (openId === id) setOpenId(null);
  };

  if (!areas.length)
    return (
      <div className="page">
        <div className="page-head">
          <h1>Model</h1>
        </div>
        <p className="placeholder">
          {mapPath ? <Link to={mapPath}>Draw or upload an area on the map</Link> : "Draw or upload an area on the map"} to
          begin.
        </p>
      </div>
    );

  if (!experiments.length)
    return (
      <div className="page">
        <div className="page-head">
          <h1>Model</h1>
        </div>
        <section className="suggestions" aria-label="Suggested experiments">
          <h2>Can the next month be forecast, and what do the models rely on?</h2>
          <div className="tiles">
            <button className="tile" onClick={() => add()}>
              <strong>The paper&apos;s method</strong>
              <span>Ridge, Random Forest and XGBoost forecast NDVI from its past, LST and SPEI.</span>
              <span className="meta">Tuned on the training years, tested on the last three, explained and compared.</span>
            </button>
            <button
              className="tile"
              onClick={() =>
                add({
                  area: firstArea,
                  response: "ndvi",
                  drivers: [],
                  own_lags: null,
                  driver_lags: null,
                  test_years: 3,
                  models: ["Ridge"],
                  params: {},
                  calendar: true,
                  rolling: true,
                })
              }
            >
              <strong>Your own recipe</strong>
              <span>Start from one model and its own past, and add what you want to test.</span>
              <span className="meta">Every choice can be changed before running.</span>
            </button>
          </div>
        </section>
      </div>
    );

  const pair = comparing.map((id) => experiments.find((e) => e.id === id)).filter((e): e is Experiment => !!e);

  return (
    <div className="page model-page">
      <div className="page-head">
        <h1>Model</h1>
        <button className="primary row" onClick={() => add()}>
          <PlusIcon size={14} />
          New experiment
        </button>
      </div>

      <div className="model-layout">
        <nav className="experiments" aria-label="Experiments">
          {experiments.map((e) => {
            const recipe = resolve(e.recipe);
            return (
              <div key={e.id} className="experiment-item" aria-current={pair.length < 2 && e.id === open?.id}>
                <button className="experiment-open" onClick={() => (setOpenId(e.id), setComparing([]))}>
                  <strong>{e.name}</strong>
                  <span className="meta">
                    {areas.find((a) => a.id === recipe?.area)?.name ?? "no area"} · {recipeLine(e.recipe, name)}
                  </span>
                  {!e.ran && <span className="meta not-run">Not run yet</span>}
                </button>
                <label className="row compare-check meta">
                  <input
                    type="checkbox"
                    checked={comparing.includes(e.id)}
                    disabled={!e.ran || (comparing.length >= 2 && !comparing.includes(e.id))}
                    onChange={(ev) =>
                      setComparing(ev.target.checked ? [...comparing, e.id] : comparing.filter((c) => c !== e.id))
                    }
                  />
                  Compare
                </label>
              </div>
            );
          })}
          <p className="meta">Tick two experiments that have run to see them side by side.</p>
        </nav>

        {seasonal ? (
          <p className="placeholder">
            Forecasts are monthly. Change the time step to native or monthly
            {dataPath ? (
              <>
                {" "}
                on the <Link to={dataPath}>Data page</Link>
              </>
            ) : null}
            .
          </p>
        ) : pair.length === 2 ? (
          <Compare pair={pair} resolve={resolve} options={options} entries={entries} areas={areas} name={name} onExplain={(id) => update(id, { explain: true })} />
        ) : (
          open && (
            <ExperimentView
              key={open.id}
              experiment={open}
              resolve={resolve}
              onChange={(change) => update(open.id, change)}
              onDuplicate={() => add({ ...open.recipe }, `${open.name} (copy)`)}
              onRemove={() => remove(open.id)}
              areas={areas}
              variables={variables}
              title={title}
              entries={entries}
              options={options}
            />
          )
        )}
      </div>
    </div>
  );
}

// Whether the series a run needs have been extracted for its area
function readyFor(r: RecipeT | null, entries: Props["entries"]): boolean {
  if (!r || r.area === null) return false;
  return [r.response, ...r.drivers].every(
    (key) => entries(key).find((e) => e.area.id === r.area)?.state?.status === "done",
  );
}

type ViewProps = {
  experiment: Experiment;
  resolve: (r: RecipeT | null) => RecipeT | null;
  onChange: (change: Partial<Experiment>) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  areas: Area[];
  variables: Variable[];
  title: (v: Variable) => string;
  entries: Props["entries"];
  options: Props["options"];
};

function ExperimentView(props: ViewProps) {
  const { experiment: e, resolve, onChange, onDuplicate, onRemove, areas, variables, title, entries, options } = props;
  const recipe = resolve(e.recipe)!;
  const ran = resolve(e.ran);
  const changed = !sameRecipe(recipe, ran);
  const runnable = recipe.models.length > 0;
  const ready = readyFor(ran, entries);
  const { fit, why } = useRun(ready && ran ? bodyOf(ran, options) : null, e.explain);

  return (
    <section className="card experiment" aria-label="Experiment">
      <div className="card-head">
        <input
          className="experiment-name"
          aria-label="Experiment name"
          defaultValue={e.name}
          onBlur={(ev) => ev.target.value.trim() && onChange({ name: ev.target.value.trim() })}
        />
        <div className="row" style={{ gap: 6 }}>
          <button className="button" onClick={onDuplicate} title="A copy to change one thing and compare">
            Duplicate
          </button>
          <button className="icon-button" aria-label="Delete this experiment" title="Delete this experiment" onClick={onRemove}>
            <CloseIcon size={14} />
          </button>
        </div>
      </div>

      <details className="recipe-box" open={!e.ran || changed}>
        <summary>Recipe</summary>
        <Recipe
          recipe={recipe}
          onChange={(r) => onChange({ recipe: r })}
          areas={areas}
          variables={variables}
          title={title}
        />
      </details>

      <div className="run-bar">
        <button
          className="primary"
          disabled={!runnable || (!changed && !!ran)}
          onClick={() => onChange({ ran: structuredClone(recipe), explain: false })}
        >
          {!ran ? "Run experiment" : changed ? "Run with these changes" : "Up to date"}
        </button>
        <span className="meta" role="status">
          {!runnable
            ? "Choose at least one model and one predictor."
            : changed && ran
              ? "The recipe has changed since the results below were made."
              : ran
                ? "The results below are from this recipe."
                : "Nothing has run yet."}
        </span>
      </div>

      {ran &&
        (ready ? (
          <Results
            fit={fit}
            why={why}
            explain={e.explain}
            onExplain={() => onChange({ explain: true })}
            digits={ran.response === "lst" ? 2 : 4}
          />
        ) : (
          <p className="placeholder">Waiting for the series of this area to load.</p>
        ))}
    </section>
  );
}

type CompareProps = {
  pair: Experiment[];
  resolve: (r: RecipeT | null) => RecipeT | null;
  options: Props["options"];
  entries: Props["entries"];
  areas: Area[];
  name: (key: VariableKey) => string;
  onExplain: (id: number) => void;
};

// Two runs side by side, with what differs between their recipes said first
function Compare({ pair, resolve, options, entries, areas, name, onExplain }: CompareProps) {
  const [a, b] = pair.map((e) => resolve(e.ran)!);
  const differences = recipeDifferences(a, b, areas, name);
  return (
    <section className="compare" aria-label="Comparison">
      <p className="compare-diff">
        <strong>What differs:</strong> {differences.length ? differences.join("; ") : "nothing: the same recipe"}.
      </p>
      <div className="compare-grid">
        {pair.map((e) => (
          <CompareColumn key={e.id} experiment={e} recipe={resolve(e.ran)!} options={options} entries={entries} onExplain={() => onExplain(e.id)} />
        ))}
      </div>
    </section>
  );
}

function CompareColumn(props: {
  experiment: Experiment;
  recipe: RecipeT;
  options: Props["options"];
  entries: Props["entries"];
  onExplain: () => void;
}) {
  const { experiment: e, recipe, options, entries, onExplain } = props;
  const ready = readyFor(recipe, entries);
  const { fit, why } = useRun(ready ? bodyOf(recipe, options) : null, e.explain);
  return (
    <section className="card" aria-label={e.name}>
      <h3>{e.name}</h3>
      {ready ? (
        <Results fit={fit} why={why} explain={e.explain} onExplain={onExplain} digits={recipe.response === "lst" ? 2 : 4} compact />
      ) : (
        <p className="placeholder">Waiting for the series of this area to load.</p>
      )}
    </section>
  );
}
