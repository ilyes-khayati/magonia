import { useState } from "react";
import type { Area, Variable, VariableKey } from "../api";
import { DEEP, DEFAULT_MODELS, MODEL_KIND, MODEL_LABEL, MODEL_NAMES, SETTABLE, type ModelName, type Recipe as RecipeT } from "../experiments";

type Props = {
  recipe: RecipeT;
  onChange: (recipe: RecipeT) => void;
  areas: Area[];
  variables: Variable[];
  title: (v: Variable) => string;
};

// "1, 2, 12" as lags; anything else is ignored
const parseLags = (text: string) =>
  [...new Set(text.split(/[\s,]+/).map(Number))]
    .filter((n) => Number.isInteger(n) && n >= 1 && n <= 36)
    .sort((a, b) => a - b);

export default function Recipe({ recipe, onChange, areas, variables, title }: Props) {
  const [lagText, setLagText] = useState(recipe.own_lags?.join(", ") ?? "");
  const set = (change: Partial<RecipeT>) => onChange({ ...recipe, ...change });
  const commitLags = () => {
    const lags = parseLags(lagText);
    setLagText(lags.join(", "));
    set({ own_lags: lags.length ? lags : null });
  };
  const toggleModel = (m: ModelName, on: boolean) =>
    set({ models: on ? MODEL_NAMES.filter((n) => n === m || recipe.models.includes(n)) : recipe.models.filter((n) => n !== m) });
  const setParam = (m: ModelName, key: string, value: number | null) => {
    const current = { ...(recipe.params[m] ?? {}) };
    if (value === null || Number.isNaN(value)) delete current[key];
    else current[key] = value;
    set({ params: { ...recipe.params, [m]: current } });
  };

  return (
    <div className="recipe">
      <div className="recipe-row">
        <label className="field">
          Area
          <select className="select" value={recipe.area ?? ""} onChange={(e) => set({ area: Number(e.target.value) })}>
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Forecast
          <select
            className="select"
            value={recipe.response}
            onChange={(e) => {
              const response = e.target.value as VariableKey;
              set({ response, drivers: recipe.drivers.filter((k) => k !== response), own_lags: null });
              setLagText("");
            }}
          >
            {variables.map((v) => (
              <option key={v.key} value={v.key}>
                {title(v)}, one month ahead
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="recipe-group">
        <legend>Predictors</legend>
        <label className="field">
          Autoregressive lags (months)
          <input
            className="input"
            value={lagText}
            placeholder="Automatic: lags whose autocorrelation stands out"
            onChange={(e) => setLagText(e.target.value)}
            onBlur={commitLags}
            onKeyDown={(e) => e.key === "Enter" && commitLags()}
          />
        </label>
        <div className="checks">
          {variables
            .filter((v) => v.key !== recipe.response)
            .map((v) => (
              <label key={v.key} className="row">
                <input
                  type="checkbox"
                  checked={recipe.drivers.includes(v.key)}
                  onChange={(e) =>
                    set({
                      drivers: e.target.checked ? [...recipe.drivers, v.key] : recipe.drivers.filter((k) => k !== v.key),
                    })
                  }
                />
                {title(v)}
              </label>
            ))}
          <label className="row">
            <input type="checkbox" checked={recipe.calendar} onChange={(e) => set({ calendar: e.target.checked })} />
            Calendar month (sine and cosine)
          </label>
        </div>
        <p className="reason">
          Each driver enters at the lag with the strongest cross-correlation with the target, 1 to 12 months earlier,
          tested against a bound corrected for autocorrelation and for picking the best of twelve lags. Lags can be
          typed instead, separated by commas.
        </p>
      </fieldset>

      <fieldset className="recipe-group">
        <legend>Models</legend>
        {([["Linear and tree models", DEFAULT_MODELS], ["Neural networks", DEEP]] as const).map(([group, names]) => (
        <div key={group} className="model-group">
        <span className="meta">{group}</span>
        <div className="model-choices">
          {names.map((m) => {
            const on = recipe.models.includes(m);
            const manual = recipe.params[m] !== undefined;
            return (
              <div key={m} className="model-choice" data-on={on}>
                <label className="row model-name">
                  <input type="checkbox" checked={on} onChange={(e) => toggleModel(m, e.target.checked)} />
                  <span>
                    <strong>{MODEL_LABEL[m]}</strong>
                    <span className="meta">{MODEL_KIND[m]}</span>
                  </span>
                </label>
                {on && (
                  <>
                    <span className="hyper-label">Hyperparameters</span>
                    <div className="segmented small" role="group" aria-label={`${MODEL_LABEL[m]} hyperparameters`}>
                      <button
                        aria-pressed={!manual}
                        onClick={() => {
                          const { [m]: _, ...rest } = recipe.params;
                          set({ params: rest });
                        }}
                      >
                        Automatic search
                      </button>
                      <button aria-pressed={manual} onClick={() => !manual && set({ params: { ...recipe.params, [m]: {} } })}>
                        Manual
                      </button>
                    </div>
                    {!manual && (
                      <p className="reason">
                        {m === "Ridge"
                          ? "Grid search over 50 values of alpha"
                          : DEEP.includes(m)
                            ? "Random search, 6 candidates"
                            : "Random search, 40 candidates"}
                        , scored by 5-fold time-series cross-validation on the training years only.
                      </p>
                    )}
                    {manual &&
                      SETTABLE[m].map((s) => (
                        <label key={s.key} className="field setting">
                          {s.label}
                          <input
                            className="input"
                            type="number"
                            min={s.min}
                            max={s.max}
                            step={s.step}
                            placeholder={`Default: ${s.fallback}`}
                            defaultValue={recipe.params[m]?.[s.key] ?? ""}
                            onBlur={(e) => setParam(m, s.key, e.target.value === "" ? null : Number(e.target.value))}
                          />
                        </label>
                      ))}
                  </>
                )}
              </div>
            );
          })}
        </div>
        </div>
        ))}
        {!recipe.models.length && <p className="reason">Choose at least one model.</p>}
      </fieldset>

      <fieldset className="recipe-group">
        <legend>Test</legend>
        <div className="recipe-row">
          <label className="field">
            Held out for testing
            <select className="select" value={recipe.test_years} onChange={(e) => set({ test_years: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => (
                <option key={n} value={n}>
                  Last {n} {n === 1 ? "year" : "years"}
                </option>
              ))}
            </select>
          </label>
          <label className="row" style={{ alignSelf: "end", paddingBottom: 8 }}>
            <input type="checkbox" checked={recipe.rolling} onChange={(e) => set({ rolling: e.target.checked })} />
            Also test on earlier windows
          </label>
        </div>
        <p className="reason">
          Always split by time, never at random. Every model is compared with persistence and climatology baselines, and
          refitted with several random seeds (20 for trees, 5 for networks) to show how much a score moves by chance.
        </p>
      </fieldset>
    </div>
  );
}
