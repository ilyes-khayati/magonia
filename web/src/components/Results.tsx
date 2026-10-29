import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ExplanationResponse, ModelsResponse } from "../api";
import { MODEL_LABEL, type ModelName } from "../experiments";
import { areaColour, type Theme } from "../theme";
import type { AnalysisState } from "../useAnalysis";

const TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" };
const TOOLTIP = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 };
const label = (name: string) => MODEL_LABEL[name as ModelName] ?? name;

type Props = {
  fit: AnalysisState<ModelsResponse> | undefined;
  why: AnalysisState<ExplanationResponse> | undefined;
  explain: boolean;
  onExplain: () => void;
  digits: number; // decimals of the forecast variable
  compact?: boolean; // side by side with another run: no chart, no predictors
};

export default function Results({ fit, why, explain, onExplain, digits, compact }: Props) {
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";
  if (!fit || fit.status === "loading")
    return (
      <p className="placeholder" role="status">
        Tuning the models on the training years, then refitting with 20 seeds and over earlier windows. This takes up to a
        minute.
      </p>
    );
  if (fit.status === "failed") return <p className="placeholder">{fit.error}</p>;

  const found = fit.data;
  const ranked = [...found.models].sort((a, b) => a.test.RMSE - b.test.RMSE);
  const fmt = (v: number) => v.toFixed(digits);
  const rolling = (rmse: number[]) => {
    const mean = rmse.reduce((a, b) => a + b, 0) / rmse.length;
    const sd = Math.sqrt(rmse.reduce((a, b) => a + (b - mean) ** 2, 0) / rmse.length);
    return `${fmt(mean)} ±${fmt(sd)}`;
  };
  const chart = found.dates.map((date, i) => {
    const row: Record<string, string | number> = { date, observed: found.observed[i] };
    for (const m of found.models) row[m.name] = m.predictions[i];
    return row;
  });

  return (
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
                  <span className="dot" style={{ background: areaColour(theme, i + 1) }} /> {label(m.name)}
                </th>
                <td>{fmt(m.test.RMSE)}</td>
                <td>{m.test.R2.toFixed(2)}</td>
                <td>{fmt(m.test.MAE)}</td>
                <td>{m.seeds.runs > 1 ? `±${fmt(m.seeds.RMSE_sd)}` : "none"}</td>
                <td>{m.rolling.length > 1 ? rolling(m.rolling.map((w) => w.RMSE)) : "–"}</td>
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

      {!compact && (
        <>
          <span className="meta">
            Test period {found.test[0]} to {found.test[1]}: observed and forecast
          </span>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={chart} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tick={TICK} tickFormatter={(d: string) => d.slice(0, 7)} minTickGap={36} />
              <YAxis
                tick={TICK}
                width={38}
                domain={["auto", "auto"]}
                tickFormatter={(v) => Number(v).toFixed(digits > 2 ? 2 : 1)}
              />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(d) => String(d).slice(0, 7)}
                formatter={(value, key) => [
                  Number(value).toFixed(digits > 2 ? 3 : 2),
                  key === "observed" ? "Observed" : label(String(key)),
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
        </>
      )}

      <ul className="summary">
        {found.summary.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      <h4 className="results-head">What each model leans on</h4>
      {why?.status === "done" ? (
        <Explanations data={why.data} />
      ) : why?.status === "failed" ? (
        <p className="placeholder">{why.error}</p>
      ) : explain ? (
        <p className="placeholder" role="status">
          Shuffling each input on held-out years, over five seeds, to see what each model leans on. This takes about a
          minute.
        </p>
      ) : (
        <button className="button" onClick={onExplain}>
          Explain the models
        </button>
      )}

      {!compact && (
        <>
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
          <details>
            <summary className="meta">Settings each model used</summary>
            <ul className="summary">
              {found.models.map((m) => (
                <li key={m.name}>
                  <strong>{label(m.name)}</strong>:{" "}
                  {Object.entries(m.params)
                    .map(([k, v]) => `${k.replace("ridge__", "")} ${typeof v === "number" ? +v.toPrecision(4) : v}`)
                    .join(", ") || "library defaults"}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </>
  );
}

const FAMILIES = ["own history", "LST", "drought", "calendar"];

// Share of each model's importance by family of inputs, and how far the models agree
function Explanations({ data }: { data: ExplanationResponse }) {
  const models = (["XGBoost", "RandomForest", "Ridge"] as const).filter((m) => data.families[m]);
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
                  {label(m)}
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
