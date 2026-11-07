import { useState } from "react";
import type {
  ExplanationResponse,
  ModelsResponse,
  StabilityResponse,
} from "../api";
import { MODEL_LABEL, type ModelName } from "../experiments";
import { areaColour, type Theme } from "../theme";
import Cautions from "./Cautions";
import { num, oneArea } from "../format";
import * as Plot from "@observablehq/plot";
import { PlotFrame, TimeChart } from "../plot/Chart";
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

export default function Results({
  fit,
  why,
  explain,
  onExplain,
  held,
  stable,
  onStable,
  digits,
  compact,
  label: axis,
}: Props) {
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";
  if (!fit || fit.status === "loading")
    return (
      <p className="placeholder" role="status">
        Tuning the models on the training years, then refitting with 20 seeds
        and over earlier windows. This takes up to a minute.
      </p>
    );
  if (fit.status === "failed")
    return <p className="placeholder">{fit.error}</p>;

  const found = fit.data;
  const ranked = [...found.models].sort((a, b) => a.test.RMSE - b.test.RMSE);
  const fmt = (v: number) => v.toFixed(digits);
  const rolling = (rmse: number[]) => {
    const mean = rmse.reduce((a, b) => a + b, 0) / rmse.length;
    const sd = Math.sqrt(
      rmse.reduce((a, b) => a + (b - mean) ** 2, 0) / rmse.length,
    );
    return `${fmt(mean)} ±${fmt(sd)}`;
  };
  const at = found.dates.map(dateOf);
  const chart = [
    {
      id: "observed",
      name: "Observed",
      colour: "var(--ink)",
      width: 2,
      points: at.map((date, i) => ({ date, value: found.observed[i] })),
    },
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
          <caption className="visually-hidden">
            Test scores of each model and baseline
          </caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">RMSE</th>
              <th scope="col">R²</th>
              <th scope="col">MAE</th>
              <th
                scope="col"
                title="Standard deviation of RMSE over refits with different seeds"
              >
                Seed noise
              </th>
              <th
                scope="col"
                title="Mean RMSE over earlier test windows of the same length"
              >
                Earlier windows
              </th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((m, i) => (
              <tr key={m.name}>
                <th scope="row">
                  <span
                    className="dot"
                    style={{ background: areaColour(theme, i + 1) }}
                  />{" "}
                  {label(m.name)}
                </th>
                <td>{fmt(m.test.RMSE)}</td>
                <td>{m.test.R2.toFixed(2)}</td>
                <td>{fmt(m.test.MAE)}</td>
                <td>
                  {m.seeds.runs > 1 ? `±${fmt(m.seeds.RMSE_sd)}` : "none"}
                </td>
                <td>
                  {m.rolling.length > 1
                    ? rolling(m.rolling.map((w) => w.RMSE))
                    : "–"}
                </td>
              </tr>
            ))}
            {(["persistence", "climatology"] as const).map((b) => (
              <tr key={b} className="baseline">
                <th scope="row">
                  {b === "persistence"
                    ? "Persistence (last month)"
                    : "Climatology (usual month)"}
                </th>
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
            Test period {found.test[0]} to {found.test[1]}: observed and
            forecast
          </span>
          <TimeChart
            title="Observed and forecast"
            series={chart}
            height={210}
            y={{
              label: axis ?? "Forecast variable",
              digits: digits > 2 ? 2 : 1,
            }}
          />
          <div className="legend">
            {chart.map((s) => (
              <span key={s.id} className="row" style={{ gap: 6 }}>
                <span
                  className="swatch"
                  style={{
                    background: s.colour,
                    height: s.id === "observed" ? 3 : 2,
                  }}
                />
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
          Shuffling each input on held-out years, over five seeds, to see what
          each model leans on. This takes about a minute.
        </p>
      ) : (
        <button className="button" onClick={onExplain}>
          Explain the models
        </button>
      )}

      {why?.status === "done" && onStable && (
        <>
          <h4 className="results-head">
            Does the explanation hold across training years?
          </h4>
          {held?.status === "done" ? (
            <Stability data={held.data} />
          ) : held?.status === "failed" ? (
            <p className="placeholder">{held.error}</p>
          ) : stable ? (
            <p className="placeholder" role="status">
              Explaining the models again on training years that end one, two
              and three years earlier. This takes a few minutes.
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
            <summary className="meta">
              Predictors and why each was chosen ({found.features.length})
            </summary>
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
                    .map(
                      ([k, v]) =>
                        `${k.replace("ridge__", "")} ${typeof v === "number" ? +v.toPrecision(4) : v}`,
                    )
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
  const models = (
    ["XGBoost", "RandomForest", "Ridge", "MLP", "LSTM", "GRU", "TCN"] as const
  ).filter((m) => data.families[m]);
  return (
    <>
      <div className="table-scroll" tabIndex={0}>
        <table className="stats models">
          <caption className="visually-hidden">
            Share of each model&apos;s importance by family of inputs
          </caption>
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
            {FAMILIES.filter((f) =>
              models.some((m) => data.families[m]?.[f] !== undefined),
            ).map((f) => (
              <tr key={f}>
                <th scope="row">{f}</th>
                {models.map((m) => {
                  const range = data.family_range?.[m]?.[f];
                  return (
                    <td
                      key={m}
                      title={
                        range
                          ? "Lowest and highest share over the seeds"
                          : undefined
                      }
                    >
                      {`${Math.round(100 * (data.families[m]?.[f] ?? 0))}%`}
                      {range && (
                        <span className="range">
                          {" "}
                          {Math.round(100 * range[0])}–
                          {Math.round(100 * range[1])}
                        </span>
                      )}
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
            <caption className="caption">
              Refitted without it: how much the error rises
            </caption>
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
              {FAMILIES.filter((f) =>
                models.some((m) => data.dropped?.[m]?.[f] !== undefined),
              ).map((f) => (
                <tr key={f}>
                  <th scope="row">{f}</th>
                  {models.map((m) => {
                    const v = data.dropped?.[m]?.[f];
                    return (
                      <td key={m}>
                        {v === undefined
                          ? "–"
                          : `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(100 * v))}%`}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.native && Object.keys(data.native).length > 0 && (
        <div className="table-scroll" tabIndex={0}>
          <table className="stats models">
            <caption className="caption">
              Each model&apos;s own explanation against shuffling
            </caption>
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">Own method</th>
                <th
                  scope="col"
                  title="Weighted Kendall's τ between the two rankings of the inputs"
                >
                  Agreement (τ)
                </th>
              </tr>
            </thead>
            <tbody>
              {models
                .filter((m) => data.native?.[m])
                .map((m) => (
                  <tr key={m}>
                    <th scope="row">{label(m)}</th>
                    <td style={{ textAlign: "left" }}>
                      {data.native![m].method}
                    </td>
                    <td>{num(data.native![m].tau, 2)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
      <LagMap data={data} models={models} />
      {data.effects && Object.keys(data.effects).length > 0 && (
        <Effects data={data} models={models} />
      )}
      {data.timeline && Object.keys(data.timeline).length > 0 && (
        <Timeline
          data={data}
          models={models.filter((m) => data.timeline?.[m])}
        />
      )}
      <ul className="summary">
        {oneArea(data.summary).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <span className="meta">
        Permutation importance on held-out training years, {data.seeds} seeds.
        Two models disagree beyond noise when their whole range lies outside how
        much each one varies with itself.
      </span>
    </>
  );
}

// The family each model leans on most when its training years end earlier
function Stability({ data }: { data: StabilityResponse }) {
  const models = (["XGBoost", "RandomForest", "Ridge"] as const).filter(
    (m) => data.leading[m],
  );
  return (
    <>
      <div className="table-scroll" tabIndex={0}>
        <table className="stats models">
          <caption className="visually-hidden">
            What each model leans on most, by training window
          </caption>
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
                      {family}{" "}
                      {Math.round(100 * (w.families[m]?.[family] ?? 0))}%
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

// Month by month, how far each family of inputs moved one model's forecast: when the
// explanation holds, and when the model leaned on something else
function Timeline({
  data,
  models,
}: {
  data: ExplanationResponse;
  models: string[];
}) {
  const [model, setModel] = useState(models[0]);
  const rows = data.timeline?.[model] ?? [];
  const families = [
    ...new Set(rows.flatMap((r) => Object.keys(r).filter((k) => k !== "date"))),
  ];
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";
  const series = families.map((f, i) => ({
    id: f,
    name: f,
    colour: areaColour(theme, i),
    width: 1.3,
    points: rows.map((r) => ({
      date: dateOf(`${r.date}-01`),
      value: Number(r[f]),
    })),
  }));
  return (
    <>
      <h4 className="results-head">What moved the forecast, month by month</h4>
      <div
        className="segmented small"
        role="group"
        aria-label="Model shown month by month"
      >
        {models.map((m) => (
          <button
            key={m}
            aria-pressed={m === model}
            onClick={() => setModel(m)}
          >
            {label(m)}
          </button>
        ))}
      </div>
      <TimeChart
        title={`What moved ${label(model)}'s forecast`}
        series={series}
        height={190}
        y={{ label: "Change in forecast", digits: 2, zero: true }}
      />
      <div className="legend">
        {series.map((s) => (
          <span key={s.id} className="row" style={{ gap: 6 }}>
            <span className="swatch" style={{ background: s.colour }} />
            {s.name}
          </span>
        ))}
      </div>
      <span className="meta">
        Each family set to its average and the forecast made again: above zero,
        that family pushed the forecast up that month.
      </span>
    </>
  );
}

// How each model's forecast responds as one of its leading inputs rises: one small chart per
// input, one line per model, so that models can be compared on shape as well as on size
function Effects({
  data,
  models,
}: {
  data: ExplanationResponse;
  models: string[];
}) {
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";
  const shown = models.filter((m) =>
    Object.values(data.effects ?? {}).some((curves) => curves[m]),
  );
  const colour = (m: string) => areaColour(theme, shown.indexOf(m) + 1);
  const chart = (
    input: string,
    curves: Record<string, { x: number; effect: number }[]>,
  ): Plot.PlotOptions => {
    const rows = shown.flatMap((m) =>
      (curves[m] ?? []).map((p) => ({ ...p, model: m })),
    );
    return {
      marginLeft: 46,
      marginBottom: 40,
      // the input's name as the axis label, so that an exported panel still says what it shows
      x: {
        label: input.replace(/_/g, " "),
        labelAnchor: "center",
        labelArrow: "none",
        labelOffset: 34,
        tickFormat: (v: number) => num(v, 2),
        ticks: 4,
      },
      y: {
        label: "Change in forecast",
        labelArrow: "none",
        grid: true,
        tickFormat: (v: number) => num(v, 2),
        ticks: 4,
      },
      color: { domain: shown, range: shown.map(colour) },
      marks: [
        Plot.ruleY([0], { stroke: "currentColor", strokeOpacity: 0.4 }),
        Plot.lineY(rows, {
          x: "x",
          y: "effect",
          z: "model",
          stroke: "model",
          strokeWidth: 1.6,
        }),
        Plot.dot(rows, { x: "x", y: "effect", fill: "model", r: 1.8 }),
        Plot.tip(
          rows,
          Plot.pointer({
            x: "x",
            y: "effect",
            title: (r: { model: string; x: number; effect: number }) =>
              `${label(r.model)}\nat ${num(r.x, 3)}: ${r.effect >= 0 ? "+" : ""}${num(r.effect, 3)}`,
          }),
        ),
      ],
    };
  };
  return (
    <>
      <h4 className="results-head">
        How the forecast responds to each leading input
      </h4>
      <div className="purity-figures">
        {Object.entries(data.effects ?? {}).map(([input, curves]) => (
          <PlotFrame
            key={input}
            title={input.replace(/_/g, " ")}
            options={chart(input, curves)}
            height={200}
          />
        ))}
      </div>
      <div className="legend">
        {shown.map((m) => (
          <span key={m} className="row" style={{ gap: 6 }}>
            <span className="swatch" style={{ background: colour(m) }} />
            {label(m)}
          </span>
        ))}
      </div>
      <span className="meta">
        Accumulated local effects: the input moved only across the values it
        really takes, a step at a time, so that lags of one series, which move
        together, are not set apart. A flat line: the model ignores that input.
      </span>
    </>
  );
}

// Which month of which input each model leans on: shuffling importance by lag, as a share of
// the model's total, one row per input series
function LagMap({
  data,
  models,
}: {
  data: ExplanationResponse;
  models: string[];
}) {
  const [model, setModel] = useState(models[0]);
  const importance = data.importance[model] ?? {};
  const total =
    Object.values(importance).reduce((a, v) => a + Math.max(0, v), 0) || 1;
  const cells = Object.entries(importance).flatMap(([feature, v]) => {
    const m = /^(.*)_lag(\d+)$/.exec(feature);
    return m
      ? [{ input: m[1], lag: Number(m[2]), share: Math.max(0, v) / total }]
      : [];
  });
  if (!cells.length) return null;
  const longest = Math.max(...cells.map((c) => c.input.length));
  const top = Math.max(...cells.map((c) => c.share));
  const percent = (c: { share: number }) => `${Math.round(100 * c.share)}%`;
  const options: Plot.PlotOptions = {
    // room for the longest input name, at about six pixels a letter
    marginLeft: Math.min(220, 20 + 6.2 * longest),
    marginBottom: 40,
    x: {
      type: "band",
      label: "Months earlier",
      labelAnchor: "center",
      labelArrow: "none",
      labelOffset: 34,
    },
    y: { type: "band", label: null },
    color: {
      scheme: "viridis",
      domain: [0, top],
    },
    marks: [
      Plot.cell(cells, { x: "lag", y: "input", fill: "share", inset: 0.5 }),
      // dark ink on the light end of the scale, white on the dark end; constant fills, as a
      // fill channel would be read through the colour scale
      Plot.text(
        cells.filter((c) => c.share > 0.5 * top),
        { x: "lag", y: "input", text: percent, fill: "black", fontSize: 10 },
      ),
      Plot.text(
        cells.filter((c) => c.share <= 0.5 * top),
        { x: "lag", y: "input", text: percent, fill: "white", fontSize: 10 },
      ),
    ],
  };
  return (
    <>
      <h4 className="results-head">Which month of which input it leans on</h4>
      <div
        className="segmented small"
        role="group"
        aria-label="Model shown by lag"
      >
        {models.map((m) => (
          <button
            key={m}
            aria-pressed={m === model}
            onClick={() => setModel(m)}
          >
            {label(m)}
          </button>
        ))}
      </div>
      <PlotFrame
        title={`Importance by lag, ${label(model)}`}
        options={options}
        height={Math.max(
          120,
          40 * new Set(cells.map((c) => c.input)).size + 60,
        )}
      />
    </>
  );
}
