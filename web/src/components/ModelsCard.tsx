import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Models } from "../analyses";
import {
  explainModels,
  fitModels,
  type ExplanationResponse,
  type ModelsBody,
  type SeriesOptions,
  type Variable,
  type VariableKey,
} from "../api";
import { areaColour, type Theme } from "../theme";
import { useAnalysis } from "../useAnalysis";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Models;
  onChange: (change: Partial<Models>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean;
};

const LABEL = { Ridge: "Ridge", RandomForest: "Random Forest", XGBoost: "XGBoost" };
const TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" };
const TOOLTIP = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 };

// "1, 2, 12" as lags; anything else is ignored
const parseLags = (text: string) =>
  [...new Set(text.split(/[\s,]+/).map(Number))].filter((n) => Number.isInteger(n) && n >= 1 && n <= 36).sort((a, b) => a - b);

export default function ModelsCard(props: Props) {
  const { analysis, onChange, onRemove, variables, title, entries, options, seasonal } = props;
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  const areas = entries(analysis.response).map((e) => e.area);
  const [picked, setPicked] = useState<number | null>(null);
  const areaId = areas.some((a) => a.id === picked) ? picked! : (areas[0]?.id ?? null);
  const [lagText, setLagText] = useState(analysis.own_lags?.join(", ") ?? "");
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";
  const digits = analysis.response === "lst" ? 2 : 4;

  const done = (key: VariableKey) => entries(key).find((e) => e.area.id === areaId)?.state?.status === "done";
  const ready = areaId !== null && !seasonal && [analysis.response, ...analysis.drivers].every(done);
  const body: ModelsBody | null = ready
    ? {
        response: options(areaId, analysis.response),
        drivers: analysis.drivers.map((k) => options(areaId, k)),
        own_lags: analysis.own_lags,
        driver_lags: analysis.driver_lags,
        test_years: analysis.test_years,
      }
    : null;
  const signature = JSON.stringify(body);
  const requests = useMemo(
    () => (signature === "null" ? [] : [{ key: signature, body: JSON.parse(signature) as ModelsBody }]),
    [signature],
  );
  const result = useAnalysis(requests, fitModels).get(signature);
  const found = result?.status === "done" ? result.data : null;

  // explaining is asked for, since it takes about a minute more
  const [explaining, setExplaining] = useState(false);
  const explainRequests = useMemo(
    () => (explaining && found ? [{ key: signature, body: JSON.parse(signature) as ModelsBody }] : []),
    [explaining, found, signature],
  );
  const why = useAnalysis(explainRequests, explainModels).get(signature);

  const ranked = found ? [...found.models].sort((a, b) => a.test.RMSE - b.test.RMSE) : [];
  const chart = found
    ? found.dates.map((date, i) => {
        const row: Record<string, string | number> = { date, observed: found.observed[i] };
        for (const m of found.models) row[m.name] = m.predictions[i];
        return row;
      })
    : [];
  const fmt = (v: number) => v.toFixed(digits);
  const rolling = (rmse: number[]) => {
    const mean = rmse.reduce((a, b) => a + b, 0) / rmse.length;
    const sd = Math.sqrt(rmse.reduce((a, b) => a + (b - mean) ** 2, 0) / rmse.length);
    return `${fmt(mean)} ±${fmt(sd)}`;
  };
  const commitLags = () => {
    const lags = parseLags(lagText);
    setLagText(lags.join(", "));
    onChange({ own_lags: lags.length ? lags : null });
  };

  return (
    <section className="card" aria-label="Forecast models">
      <div className="card-head">
        <div>
          <h3>Forecast models</h3>
          <span className="meta">
            Ridge, Random Forest and XGBoost forecast {name(analysis.response)} one month ahead, tested on the last{" "}
            {analysis.test_years} years
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <label className="field" style={{ minWidth: 0 }}>
          Forecast
          <select
            className="select"
            value={analysis.response}
            onChange={(e) => {
              const response = e.target.value as VariableKey;
              onChange({ response, drivers: analysis.drivers.filter((k) => k !== response), own_lags: null });
              setLagText("");
            }}
          >
            {variables.map((v) => (
              <option key={v.key} value={v.key}>
                {title(v)}
              </option>
            ))}
          </select>
        </label>
        {areas.length > 1 ? (
          <label className="field" style={{ minWidth: 0 }}>
            Area
            <select className="select" value={areaId ?? ""} onChange={(e) => setPicked(Number(e.target.value))}>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="field" style={{ minWidth: 0 }}>
            Test years
            <select
              className="select"
              value={analysis.test_years}
              onChange={(e) => onChange({ test_years: Number(e.target.value) })}
            >
              {[2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  Last {n} years
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field" style={{ minWidth: 0 }}>
          Its own lags (months)
          <input
            className="select"
            value={lagText}
            placeholder="Recommended by the code"
            onChange={(e) => setLagText(e.target.value)}
            onBlur={commitLags}
            onKeyDown={(e) => e.key === "Enter" && commitLags()}
          />
        </label>
        <fieldset className="drivers">
          <legend>Drivers (lags chosen by the lag test)</legend>
          {variables
            .filter((v) => v.key !== analysis.response)
            .map((v) => (
              <label key={v.key} className="row" style={{ gap: 6, fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={analysis.drivers.includes(v.key)}
                  onChange={(e) =>
                    onChange({
                      drivers: e.target.checked
                        ? [...analysis.drivers, v.key]
                        : analysis.drivers.filter((k) => k !== v.key),
                    })
                  }
                />
                {title(v)}
              </label>
            ))}
        </fieldset>
      </div>

      {seasonal ? (
        <p className="placeholder">Forecasts are monthly. Change the time step on the left to native or monthly.</p>
      ) : result?.status === "failed" ? (
        <p className="placeholder">{result.error}</p>
      ) : !found ? (
        <p className="placeholder" role="status">
          {ready
            ? "Tuning three models on the training years, then refitting with 20 seeds and over earlier windows. This takes up to a minute."
            : "Waiting for the series to load."}
        </p>
      ) : (
        <>
          <div className="table-scroll">
            <table className="stats models">
              <caption className="visually-hidden">Test scores of each model and baseline</caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">RMSE</th>
                  <th scope="col">R²</th>
                  <th scope="col">MAE</th>
                  <th scope="col" title="Standard deviation of RMSE over refits with different seeds">
                    Seed noise
                  </th>
                  <th scope="col" title="Mean RMSE over earlier test windows of the same length">
                    Earlier windows
                  </th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((m, i) => (
                  <tr key={m.name}>
                    <th scope="row">
                      <span className="dot" style={{ background: areaColour(theme, i + 1) }} /> {LABEL[m.name]}
                    </th>
                    <td>{fmt(m.test.RMSE)}</td>
                    <td>{m.test.R2.toFixed(2)}</td>
                    <td>{fmt(m.test.MAE)}</td>
                    <td>{m.seeds.runs > 1 ? `±${fmt(m.seeds.RMSE_sd)}` : "none"}</td>
                    <td>{m.rolling.length ? rolling(m.rolling.map((w) => w.RMSE)) : "–"}</td>
                  </tr>
                ))}
                {(["persistence", "climatology"] as const).map((b) => (
                  <tr key={b} className="baseline">
                    <th scope="row">{b === "persistence" ? "Persistence (last month)" : "Climatology (usual month)"}</th>
                    <td>{fmt(found.baselines[b].RMSE)}</td>
                    <td>{found.baselines[b].R2.toFixed(2)}</td>
                    <td>{fmt(found.baselines[b].MAE)}</td>
                    <td />
                    <td />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <span className="meta">
            Test period {found.test[0]} to {found.test[1]}: observed and forecast
          </span>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={chart} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tick={TICK} tickFormatter={(d: string) => d.slice(0, 7)} minTickGap={36} />
              <YAxis tick={TICK} width={38} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(digits > 2 ? 2 : 1)} />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(d) => String(d).slice(0, 7)}
                formatter={(value, key) => [
                  Number(value).toFixed(digits > 2 ? 3 : 2),
                  key === "observed" ? "Observed" : LABEL[key as keyof typeof LABEL],
                ]}
              />
              <Line dataKey="observed" stroke="var(--ink)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
              {ranked.map((m, i) => (
                <Line
                  key={m.name}
                  dataKey={m.name}
                  stroke={areaColour(theme, i + 1)}
                  strokeWidth={1.4}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          <ul className="summary">
            {found.summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {why?.status === "done" ? (
            <Explanations data={why.data} />
          ) : why?.status === "failed" ? (
            <p className="placeholder">{why.error}</p>
          ) : explaining ? (
            <p className="placeholder" role="status">
              Shuffling each input on held-out years, over five seeds, to see what each model leans on. This takes about
              a minute.
            </p>
          ) : (
            <button className="button" onClick={() => setExplaining(true)}>
              Explain the models: what does each one lean on?
            </button>
          )}
          <details>
            <summary className="meta">Predictors and why each was chosen ({found.features.length})</summary>
            <ul className="summary">
              {found.features.map((f) => (
                <li key={f.name}>
                  <strong>{f.name}</strong>: {f.reason}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}

const FAMILIES = ["own history", "LST", "drought", "calendar"];

// Share of each model's importance by family of inputs, and how far the models agree
function Explanations({ data }: { data: ExplanationResponse }) {
  const models = ["XGBoost", "RandomForest", "Ridge"] as const;
  return (
    <>
      <div className="table-scroll">
        <table className="stats models">
          <caption className="visually-hidden">Share of each model&apos;s importance by family of inputs</caption>
          <thead>
            <tr>
              <th scope="col">Leans on</th>
              {models.map((m) => (
                <th key={m} scope="col">
                  {LABEL[m]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FAMILIES.filter((f) => models.some((m) => data.families[m]?.[f] !== undefined)).map((f) => (
              <tr key={f}>
                <th scope="row">{f}</th>
                {models.map((m) => (
                  <td key={m}>{`${Math.round(100 * (data.families[m]?.[f] ?? 0))}%`}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="summary">
        {data.summary.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <span className="meta">
        Permutation importance on held-out training years, {data.seeds} seeds. Two models disagree beyond noise when their
        whole range lies outside how much each one varies with itself.
      </span>
    </>
  );
}
