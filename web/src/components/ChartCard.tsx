import * as Plot from "@observablehq/plot";
import { useMemo, useState } from "react";
import type { Area, Variable } from "../api";
import { describe, median, MONTHS, observations, quantile, SEASONS, seasonalCycle } from "../stats";
import type { SeriesState } from "../useSeries";
import { InfoIcon } from "./Icons";
import { large } from "../variables";
import LearnPanel from "./LearnPanel";
import { PlotFrame, TimeChart } from "../plot/Chart";
import { source, timeSeries, yLabel } from "../plot/series";
import { num } from "../format";

export type Entry = { area: Area; colour: string; state: SeriesState | undefined };

type Props = {
  variable: Variable;
  title: string;
  entries: Entry[];
  mode: "series" | "seasonal" | "distribution";
  shown?: string | null; // how the values were changed for display, said under the title
  anomaly?: boolean; // values centred on zero, so the axis follows the data
  hidden?: number[]; // areas left out of the chart
  onHidden?: (ids: number[]) => void; // without it, the card starts from hidden and keeps its own choice
  pickAreas?: boolean; // false when the page chooses the areas for every chart at once
};

// Up to this many areas, each can be shown on its own with one click
const PICKABLE = 5;

const AXES: Record<string, { domain?: [number, number]; digits: number; ticks?: number[] }> = {
  ndvi: { domain: [0, 1], digits: 1 },
  savi: { domain: [0, 1], digits: 1 },
  evi: { domain: [0, 1], digits: 1 },
  fpar: { domain: [0, 1], digits: 1 },
  lst: { digits: 0 },
  spei: { domain: [-3, 3], digits: 0, ticks: [-3, -2, -1, 0, 1, 2, 3] },
};

const DIVERGING = new Set(["spei", "ndmi", "nbr"]);

function download(title: string, entries: Entry[]) {
  const lines = ["area,date,value,sd,n_pixels,masked,filled"];
  for (const { area, state } of entries) {
    if (state?.status !== "done") continue;
    for (const p of state.data.points) {
      lines.push([JSON.stringify(area.name), p.date, p.value ?? "", p.sd ?? "", p.n_pixels, p.masked, p.filled].join(","));
    }
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  link.download = `${title.replace(/\W+/g, "-").toLowerCase()}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

export default function ChartCard({ variable, title, entries, mode, shown: changed, anomaly, hidden, onHidden, pickAreas = true }: Props) {
  const [provenance, setProvenance] = useState(false);
  const [about, setAbout] = useState(false);
  const [ownHidden, setOwnHidden] = useState<number[]>(hidden ?? []);
  const off = new Set(onHidden ? (hidden ?? []) : ownHidden);
  const setOff = (ids: Set<number>) => (onHidden ?? setOwnHidden)([...ids]);
  const only = (id: number) => setOff(new Set(entries.map((e) => e.area.id).filter((x) => x !== id)));
  const auto: (typeof AXES)[string] = { digits: large(variable.key) ? 0 : 2 };
  const axis = anomaly ? auto : (AXES[variable.key] ?? auto);
  const shown = entries.filter((e) => !off.has(e.area.id) && e.state?.status === "done");
  const warnings = [...new Set(entries.flatMap((e) => (e.state?.status === "done" ? e.state.data.warnings : [])))];
  const subtitle =
    mode === "series"
      ? `${variable.sampling === "centre" ? "Value of the grid cell at the area's centre" : "Area mean with ±1 SD of pixels"}${variable.units ? ` · ${variable.units}` : ""}`
      : mode === "seasonal"
        ? `Average year, shaded from the lowest to the highest year${variable.units ? ` · ${variable.units}` : ""}`
        : `Every observation, by calendar month, season or as a whole: median, quartiles and outliers${variable.units ? ` · ${variable.units}` : ""}`;

  function flip(id: number) {
    const next = new Set(off);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOff(next);
  }

  return (
    <section className="card" aria-label={`${title} chart`}>
      <div className="card-head">
        <div>
          <h3>{title}</h3>
          <span className="meta">
            {subtitle}
            {changed && ` · ${changed}`}
          </span>
        </div>
        <div className="row" style={{ gap: 6 }}>
          {variable.learn && (
            <button className="text-button" aria-expanded={about} onClick={() => setAbout(!about)}>
              What is {variable.name.length <= 6 ? variable.name : "this"}?
            </button>
          )}
          <button className="text-button" onClick={() => download(title, entries)} disabled={!shown.length}>
            CSV
          </button>
          <button
            className="icon-button"
            aria-label="Where this comes from"
            title="Where this comes from"
            aria-expanded={provenance}
            onClick={() => setProvenance(!provenance)}
          >
            <InfoIcon size={14} />
          </button>
        </div>
      </div>

      {about && <LearnPanel variable={variable} />}

      {pickAreas && entries.length > 1 && entries.length <= PICKABLE && (
        <div className="segmented small area-choice" role="group" aria-label={`Areas in the ${title} chart`}>
          <button aria-pressed={off.size === 0} onClick={() => setOff(new Set())}>
            Together
          </button>
          {entries.map(({ area }) => (
            <button
              key={area.id}
              aria-pressed={off.size === entries.length - 1 && !off.has(area.id)}
              onClick={() => only(area.id)}
            >
              {area.name}
            </button>
          ))}
        </div>
      )}

      {mode === "series" ? (
        <TimeChart
          title={title}
          series={timeSeries(shown)}
          height={220}
          y={{ label: yLabel(variable), digits: axis.digits, domain: axis.domain, ticks: axis.ticks, zero: DIVERGING.has(variable.key) || anomaly }}
          source={source(variable)}
        />
      ) : mode === "seasonal" ? (
        <SeasonalChart title={title} shown={shown} label={yLabel(variable)} digits={axis.digits} domain={axis.domain} source={source(variable)} />
      ) : (
        <DistributionChart title={title} shown={shown} label={yLabel(variable)} digits={axis.digits} domain={axis.domain} source={source(variable)} />
      )}

      <div className="legend">
        {entries.map(({ area, colour, state }) => (
          <button key={area.id} aria-pressed={!off.has(area.id)} onClick={() => flip(area.id)}>
            <span className="swatch" style={{ background: colour }} />
            {area.name}
            {state?.status === "loading" && <span className="meta"> · loading…</span>}
            {state?.status === "failed" && <span className="error-text"> · {state.error}</span>}
          </button>
        ))}
        {mode === "series" && <span className="meta">○ filled value</span>}
      </div>

      {warnings.map((warning) => (
        <p key={warning} className="warning">
          {warning}
        </p>
      ))}

      {mode === "series" && shown.length > 0 && (
        <table className="stats">
          <caption className="visually-hidden">Descriptive statistics of real observations</caption>
          <thead>
            <tr>
              <th scope="col">Area</th>
              <th scope="col">Mean</th>
              <th scope="col">Min</th>
              <th scope="col">Max</th>
              <th scope="col">SD</th>
              <th scope="col" title="Months with a real observation">
                Observed
              </th>
              <th scope="col" title="Short gaps filled by interpolation, set on the Data panel">
                Gap-filled
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map(({ area, state }) => {
              const s = state?.status === "done" ? describe(state.data.points) : null;
              const f = (x: number) => num(x, axis.digits + 1);
              return (
                <tr key={area.id}>
                  <th scope="row">{area.name}</th>
                  <td>{s ? f(s.mean) : "–"}</td>
                  <td>{s ? f(s.min) : "–"}</td>
                  <td>{s ? f(s.max) : "–"}</td>
                  <td>{s ? f(s.sd) : "–"}</td>
                  <td>{s ? s.n : "–"}</td>
                  <td>{s ? s.filled : "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {provenance && (
        <div className="provenance">
          {entries.map(({ area, state }) =>
            state?.status === "done" ? <Provenance key={area.id} name={area.name} record={state.data.provenance} /> : null,
          )}
        </div>
      )}
    </section>
  );
}

// The average year: months on the axis, shaded from the lowest to the highest year
function SeasonalChart({ title, shown, label, digits, domain, source }: { title: string; shown: Entry[]; label: string; digits: number; domain?: [number, number]; source: string }) {
  const [centre, setCentre] = useState<"mean" | "median">("mean");
  const options = useMemo<Plot.PlotOptions>(() => {
    const rows = shown.flatMap(({ area, colour, state }) =>
      state?.status === "done" ? seasonalCycle(state.data.points).map((m) => ({ ...m, id: area.id, colour })) : [],
    );
    return {
      x: { domain: [0, 11], ticks: 12, tickFormat: (m: number) => MONTHS[m] ?? "", label: null, tickSize: 4 },
      y: { label, labelArrow: "none", domain, grid: true, nice: !domain, tickFormat: (v: number) => num(v, digits), tickSize: 0 },
      marks: [
        Plot.areaY(rows, { x: "month", y1: "low", y2: "high", z: "id", fill: "colour", fillOpacity: 0.13 }),
        Plot.lineY(rows, { x: "month", y: centre, z: "id", stroke: "colour", strokeWidth: 1.5 }),
        Plot.dot(rows, { x: "month", y: centre, fill: "colour", r: 2 }),
        Plot.tip(
          rows,
          Plot.pointerX({
            x: "month",
            y: centre,
            title: (r: { month: number; mean: number; median: number; years: number }) =>
              `${MONTHS[r.month]}\nmean ${num(r.mean, digits + 1)} · median ${num(r.median, digits + 1)}\n${r.years} values`,
          }),
        ),
      ],
    };
  }, [shown, label, digits, domain, centre]);
  return (
    <>
      <div className="segmented small" role="group" aria-label="Middle of each month">
        <button aria-pressed={centre === "mean"} onClick={() => setCentre("mean")}>
          Mean
        </button>
        <button aria-pressed={centre === "median"} onClick={() => setCentre("median")}>
          Median
        </button>
      </div>
      <PlotFrame title={title} options={options} height={200} source={source} />
    </>
  );
}

type Grouping = "month" | "season" | "all";

// Boxplots of every observation: by calendar month, by season, or all together, one box per area
function DistributionChart({ title, shown, label, digits, domain, source }: { title: string; shown: Entry[]; label: string; digits: number; domain?: [number, number]; source: string }) {
  const [by, setBy] = useState<Grouping>("month");
  const options = useMemo<Plot.PlotOptions>(() => {
    const rows = shown.flatMap(({ area, colour, state }) =>
      state?.status === "done" ? observations(state.data.points).map((o) => ({ ...o, area: area.name, colour })) : [],
    );
    const names = shown.map((e) => e.area.name);
    const colours = shown.map((e) => e.colour);
    const group = by === "month" ? (r: { month: number }) => MONTHS[r.month] : by === "season" ? (r: { season: string }) => r.season : () => "All";
    const groups = by === "month" ? MONTHS : by === "season" ? [...SEASONS] : ["All"];
    const summary: Summary[] = [];
    for (const g of groups) {
      for (const name of names) {
        const values = rows.filter((r) => group(r as never) === g && r.area === name).map((r) => r.value);
        if (values.length) summary.push({ group: g, area: name, n: values.length, median: median(values), q1: quantile(values, 0.25), q3: quantile(values, 0.75) });
      }
    }
    return {
      fx: { domain: groups, label: null, padding: 0.08 },
      x: { domain: names, axis: null, padding: 0.2 },
      y: { label, labelArrow: "none", domain, grid: true, nice: !domain, tickFormat: (v: number) => num(v, digits), tickSize: 0 },
      color: { domain: names, range: colours },
      marks: [
        Plot.boxY(rows, { fx: group, x: "area", y: "value", fill: "area", stroke: "area", fillOpacity: 0.25, r: 1.5 }),
        Plot.tip(summary, Plot.pointer({ fx: "group", x: "area", y: "median", title: (r: Summary) => `${r.area}, ${r.group}\nmedian ${num(r.median, digits + 1)} · IQR ${num(r.q1, digits + 1)} – ${num(r.q3, digits + 1)}\n${r.n} values` })),
      ],
    };
  }, [shown, label, digits, domain, by]);
  return (
    <>
      <div className="segmented small" role="group" aria-label="Group the observations">
        <button aria-pressed={by === "month"} onClick={() => setBy("month")}>
          By month
        </button>
        <button aria-pressed={by === "season"} onClick={() => setBy("season")}>
          By season
        </button>
        <button aria-pressed={by === "all"} onClick={() => setBy("all")}>
          All together
        </button>
      </div>
      <PlotFrame title={title} options={options} height={by === "all" ? 200 : 230} source={source} />
    </>
  );
}

type Summary = { group: string; area: string; n: number; median: number; q1: number; q3: number };

type Step = { step: string; [key: string]: unknown };

function Provenance({ name, record }: { name: string; record: Record<string, unknown> }) {
  const v = record.variable as Record<string, string>;
  const area = record.area as Record<string, string | number>;
  const window = record.window as Record<string, string>;
  const steps = record.steps as Step[];
  const describeStep = (s: Step) =>
    Object.entries(s)
      .filter(([key]) => key !== "step")
      .map(([key, value]) => `${key.replace(/_/g, " ")}: ${value}`)
      .join(", ");

  return (
    <dl>
      <dt className="provenance-title">{name}</dt>
      <dt>Product</dt>
      <dd>
        {v.product} · <code>{v.band}</code>
      </dd>
      <dt>Licence</dt>
      <dd>{v.licence}</dd>
      <dt>Area</dt>
      <dd>
        {area.area_km2} km² · {area.sampling}
      </dd>
      <dt>Window</dt>
      <dd>
        {window.start} to {window.end} (end excluded)
      </dd>
      {steps.map((s) => (
        <div key={s.step} style={{ display: "contents" }}>
          <dt>{s.step}</dt>
          <dd>{describeStep(s)}</dd>
        </div>
      ))}
      <dt>Citation</dt>
      <dd>{v.citation}</dd>
      <dt>Provenance id</dt>
      <dd>
        <code>{String(record.id)}</code>
      </dd>
    </dl>
  );
}
