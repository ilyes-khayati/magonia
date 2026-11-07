import { useEffect, useState } from "react";
import { Link } from "react-router";
import { downloadNotebook, type Area, type SeriesOptions, type Variable, type VariableKey } from "../api";
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
import type { Source } from "../board";
import { useRun } from "../useRun";
import Results from "./Results";
import { large } from "../variables";

type Props = {
  experiments: Experiment[];
  onChange: (experiments: Experiment[]) => void;
  onRemove: (id: number) => void; // deleted with an Undo
  areas: Area[];
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean; // seasonal means cannot be forecast month by month
  dataPath: string | null;
  mapPath: string | null;
  onShown: (ids: number[]) => void; // the experiments on screen, which Magonia is told about
  onPin?: (card: HTMLElement, title: string, source: Source) => void;
};

// Forecasting experiments, kept like the runs of a notebook: each has its recipe and its
// results, and two can be put side by side
export default function ModelPage(props: Props) {
  const { experiments, onChange, onRemove, areas, variables, title, entries, options, seasonal, dataPath, mapPath, onShown } = props;
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
    onRemove(id);
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
              <strong>New experiment</strong>
              <span>Choose what to forecast, from which predictors, with which models.</span>
              <span className="meta">
                Each run is split by time, compared with persistence and climatology, and refitted with several seeds to
                show how much a score moves by chance.
              </span>
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
                <button className="experiment-open" title={recipeLine(e.recipe, name)} onClick={() => (setOpenId(e.id), setComparing([]))}>
                  <strong>{e.name}</strong>
                  <span className="meta">
                    {name(e.recipe.response)} · {areas.find((a) => a.id === recipe?.area)?.name ?? "no area"}
                  </span>
                  <span className="meta">
                    {e.recipe.models.length} model{e.recipe.models.length === 1 ? "" : "s"} · {e.recipe.drivers.length} driver
                    {e.recipe.drivers.length === 1 ? "" : "s"} · {e.recipe.test_years} years held out
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
              onPin={props.onPin}
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
  onPin?: (card: HTMLElement, title: string, source: Source) => void;
  areas: Area[];
  variables: Variable[];
  title: (v: Variable) => string;
  entries: Props["entries"];
  options: Props["options"];
};

function ExperimentView(props: ViewProps) {
  const { experiment: e, resolve, onChange, onDuplicate, onRemove, onPin, areas, variables, title, entries, options } = props;
  const recipe = resolve(e.recipe)!;
  const ran = resolve(e.ran);
  const changed = !sameRecipe(recipe, ran);
  const runnable = recipe.models.length > 0;
  const ready = readyFor(ran, entries);
  const { fit, why, held } = useRun(ready && ran ? bodyOf(ran, options) : null, e.explain, e.stability);

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
          {ran && ready && fit?.status === "done" && onPin && (
            <button
              className="button"
              title="Keep this run's results on the board, as they are now"
              onClick={(ev) => {
                const card = (ev.currentTarget as HTMLElement).closest<HTMLElement>(".experiment");
                if (card) onPin(card, e.name, { type: "experiment", experiment: structuredClone(e) });
              }}
            >
              Pin
            </button>
          )}
          {ran && ready && (
            <button
              className="button"
              title="A Python notebook that reproduces this run from its data"
              onClick={() => {
                const body = bodyOf(ran, options);
                downloadNotebook({
                  title: e.name,
                  kind: "experiment",
                  options: { ...ran, area: undefined },
                  series: [body.response, ...body.drivers],
                }).catch(() => undefined);
              }}
            >
              Notebook
            </button>
          )}
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
        {ran && !changed ? (
          <span className="state">Up to date</span>
        ) : (
          <button className="primary" disabled={!runnable} onClick={() => onChange({ ran: structuredClone(recipe), explain: false, stability: false })}>
            {!ran ? "Run experiment" : "Run with these changes"}
          </button>
        )}
        <span className="meta" role="status">
          {!runnable
            ? "Choose at least one model to run."
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
            held={held}
            stable={e.stability}
            onStable={() => onChange({ stability: true })}
            digits={large(ran.response) ? 2 : 4}
            label={variables.find((v) => v.key === ran.response) ? title(variables.find((v) => v.key === ran.response)!) : ran.response}
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
        <Results fit={fit} why={why} explain={e.explain} onExplain={onExplain} digits={large(recipe.response) ? 2 : 4} compact />
      ) : (
        <p className="placeholder">Waiting for the series of this area to load.</p>
      )}
    </section>
  );
}
