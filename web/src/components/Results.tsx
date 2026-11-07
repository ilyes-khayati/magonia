import type { ExplanationResponse, ModelsResponse, StabilityResponse } from "../api";
import { MODEL_LABEL, type ModelName } from "../experiments";
import { areaColour, type Theme } from "../theme";
import Cautions from "./Cautions";
import { oneArea } from "../format";
import { TimeChart } from "../plot/Chart";
import { dateOf } from "../plot/time";
import type { AnalysisState } from "../useAnalysis";

const label = (name: string) => MODEL_LABEL[name as ModelName] ?? name;

type Props = {
  fit: AnalysisState<ModelsResponse> | undefined;
  why: AnalysisState<ExplanationResponse> | undefined;
  explain: boolean;
  onExplain: () => void;
  held?: AnalysisState<StabilityResponse> | undefined;
  stable?: boolean; // the stability check asked for
  onStable?: () => void;
  digits: number; // decimals of the forecast variable
  compact?: boolean; // side by side with another run: no chart, no predictors
  label?: string; // the forecast variable, for the chart's axis
};

export default function Results({ fit, why, explain, onExplain, held, stable, onStable, digits, compact, label: axis }: Props) {
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
  const at = found.dates.map(dateOf);
  const chart = [
    { id: "observed", name: "Observed", colour: "var(--ink)", width: 2, points: at.map((date, i) => ({ date, value: found.observed[i] })) },
    ...ranked.map((m, i) => ({
      id: m.name,
      name: label(m.name),
      colour: areaColour(theme, i + 1),
      width: 1.2,
      points: at.map((date, j) => ({ date, value: m.predictions[j] })),
    })),
  ];

  return (
    <>
      <div className="table-scroll" tabIndex={0}>
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
          <TimeChart title="Observed and forecast" series={chart} height={210} y={{ label: axis ?? "Forecast variable", digits: digits > 2 ? 2 : 1 }} />
          <div className="legend">
            {chart.map((s) => (
              <span key={s.id} className="row" style={{ gap: 6 }}>
                <span className="swatch" style={{ background: s.colour, height: s.id === "observed" ? 3 : 2 }} />
                {s.name}
              </span>
            ))}
          </div>
        </>
      )}

      <ul className="summary">
        {oneArea(found.summary).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <Cautions items={found.cautions} />

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

      {why?.status === "done" && onStable && (
        <>
          <h4 className="results-head">Does the explanation hold across training years?</h4>
          {held?.status === "done" ? (
            <Stability data={held.data} />
          ) : held?.status === "failed" ? (
            <p className="placeholder">{held.error}</p>
          ) : stable ? (
            <p className="placeholder" role="status">
              Explaining the models again on training years that end one, two and three years earlier. This takes a few
              minutes.
            </p>
          ) : (
            <button className="button" onClick={onStable}>
              Check across training windows
            </button>
          )}
        </>
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
      <div className="table-scroll" tabIndex={0}>
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
                {models.map((m) => {
                  const range = data.family_range?.[m]?.[f];
                  return (
                    <td key={m} title={range ? "Lowest and highest share over the seeds" : undefined}>
                      {`${Math.round(100 * (data.families[m]?.[f] ?? 0))}%`}
                      {range && <span className="range"> {Math.round(100 * range[0])}–{Math.round(100 * range[1])}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.dropped && Object.keys(data.dropped).length > 0 && (
        <div className="table-scroll" tabIndex={0}>
          <table className="stats models">
            <caption className="caption">Refitted without it: how much the error rises</caption>
            <thead>
              <tr>
                <th scope="col">Left out</th>
                {models.map((m) => (
                  <th key={m} scope="col">
                    {label(m)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FAMILIES.filter((f) => models.some((m) => data.dropped?.[m]?.[f] !== undefined)).map((f) => (
                <tr key={f}>
                  <th scope="row">{f}</th>
                  {models.map((m) => {
                    const v = data.dropped?.[m]?.[f];
                    return <td key={m}>{v === undefined ? "–" : `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(100 * v))}%`}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="summary">
        {oneArea(data.summary).map((line) => (
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

// The family each model leans on most when its training years end earlier
function Stability({ data }: { data: StabilityResponse }) {
  const models = (["XGBoost", "RandomForest", "Ridge"] as const).filter((m) => data.leading[m]);
  return (
    <>
      <div className="table-scroll" tabIndex={0}>
        <table className="stats models">
          <caption className="visually-hidden">What each model leans on most, by training window</caption>
          <thead>
            <tr>
              <th scope="col">Trained up to</th>
              {models.map((m) => (
                <th key={m} scope="col">
                  {label(m)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.windows.map((w, i) => (
              <tr key={w.train_end}>
                <th scope="row">{w.train_end}</th>
                {models.map((m) => {
                  const family = data.leading[m][i];
                  const changed = new Set(data.leading[m]).size > 1;
                  return (
                    <td key={m} className={changed ? "unstable" : undefined}>
                      {family} {Math.round(100 * (w.families[m]?.[family] ?? 0))}%
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="summary">
        {oneArea(data.summary).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </>
  );
}
