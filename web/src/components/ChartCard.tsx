import { useState } from "react";
import {
  Area as Band,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Area, Variable } from "../api";
import { describe, MONTHS, seasonalCycle } from "../stats";
import type { SeriesState } from "../useSeries";
import { InfoIcon } from "./Icons";

export type Entry = { area: Area; colour: string; state: SeriesState | undefined };

type Props = {
  variable: Variable;
  title: string;
  entries: Entry[];
  mode: "series" | "seasonal";
  shown?: string | null; // how the values were changed for display, said under the title
  anomaly?: boolean; // values centred on zero, so the axis follows the data
};

type Row = Record<string, string | number | boolean | [number, number] | null>;

const AXES: Record<string, { domain: [number | string, number | string]; digits: number; ticks?: number[] }> = {
  ndvi: { domain: [0, 1], digits: 2 },
  lst: { domain: ["dataMin - 2", "dataMax + 2"], digits: 0 },
  spei: { domain: [-3, 3], digits: 0, ticks: [-3, -2, -1, 0, 1, 2, 3] },
};

// One row per date (or calendar month), one column per area
function rows(entries: Entry[], mode: Props["mode"]): Row[] {
  const table = new Map<string, Row>();
  for (const { area, state } of entries) {
    if (state?.status !== "done") continue;
    if (mode === "seasonal") {
      for (const m of seasonalCycle(state.data.points)) {
        const row = table.get(String(m.month)) ?? { order: m.month, label: MONTHS[m.month] };
        row[`v${area.id}`] = m.mean;
        row[`b${area.id}`] = [m.low, m.high];
        table.set(String(m.month), row);
      }
      continue;
    }
    for (const p of state.data.points) {
      const row = table.get(p.date) ?? { order: p.date, label: p.date };
      row[`v${area.id}`] = p.value;
      row[`f${area.id}`] = p.filled;
      row[`b${area.id}`] = p.value !== null && p.sd !== null ? [p.value - p.sd, p.value + p.sd] : null;
      table.set(p.date, row);
    }
  }
  return [...table.values()].sort((a, b) => (a.order! < b.order! ? -1 : 1));
}

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

export default function ChartCard({ variable, title, entries, mode, shown: changed, anomaly }: Props) {
  const [provenance, setProvenance] = useState(false);
  const [off, setOff] = useState<Set<number>>(new Set());
  const axis = anomaly ? { domain: ["auto", "auto"] as [string, string], digits: variable.key === "lst" ? 0 : 2 } : AXES[variable.key];
  const data = rows(entries, mode);
  const shown = entries.filter((e) => !off.has(e.area.id) && e.state?.status === "done");
  const warnings = [...new Set(entries.flatMap((e) => (e.state?.status === "done" ? e.state.data.warnings : [])))];
  const subtitle =
    mode === "series"
      ? `${variable.key === "spei" ? "Grid-cell value" : "Area mean"} with ±1 SD of pixels${variable.units ? ` · ${variable.units}` : ""}`
      : `Average year, shaded from the lowest to the highest year${variable.units ? ` · ${variable.units}` : ""}`;

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
          <button className="text-button" onClick={() => download(title, entries)} disabled={!shown.length}>
            CSV
          </button>
          <button
            className="icon-button round"
            aria-label="Where this comes from"
            title="Where this comes from"
            aria-expanded={provenance}
            onClick={() => setProvenance(!provenance)}
          >
            <InfoIcon size={14} />
          </button>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={mode === "series" && data.length > 24 ? 210 : 180}>
        <ComposedChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" }}
            tickFormatter={(label: string) => (mode === "series" ? label.slice(0, 7) : label)}
            minTickGap={36}
          />
          <YAxis
            domain={axis.domain}
            ticks={axis.ticks}
            tickFormatter={(value) => Number(value).toFixed(axis.digits)}
            tick={{ fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" }}
            width={34}
          />
          {variable.key === "spei" && <ReferenceLine y={0} stroke="var(--zero)" />}
          <Tooltip
            contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 }}
            formatter={(value, name) => {
              const id = Number(String(name).slice(1));
              const area = entries.find((e) => e.area.id === id)?.area.name ?? name;
              return Array.isArray(value)
                ? [`${Number(value[0]).toFixed(axis.digits + 1)} – ${Number(value[1]).toFixed(axis.digits + 1)}`, `${area} range`]
                : [Number(value).toFixed(axis.digits + 1), area];
            }}
          />
          {shown.map(({ area, colour }) => (
            <Band
              key={`b${area.id}`}
              dataKey={`b${area.id}`}
              stroke="none"
              fill={colour}
              fillOpacity={0.14}
              isAnimationActive={false}
              connectNulls={false}
            />
          ))}
          {shown.map(({ area, colour }) => (
            <Line
              key={`v${area.id}`}
              dataKey={`v${area.id}`}
              stroke={colour}
              strokeWidth={1.8}
              isAnimationActive={false}
              // filled values are drawn as hollow points so they never pass for observations
              dot={(props: { cx?: number; cy?: number; payload?: Row; index?: number }) =>
                props.payload?.[`f${area.id}`] ? (
                  <circle key={props.index} cx={props.cx} cy={props.cy} r={3} fill="var(--card)" stroke={colour} strokeWidth={1.5} />
                ) : (
                  <g key={props.index} />
                )
              }
            />
          ))}
          {mode === "series" && data.length > 24 && (
            <Brush dataKey="label" height={18} stroke="var(--muted)" fill="var(--card)" tickFormatter={() => ""} />
          )}
        </ComposedChart>
      </ResponsiveContainer>

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
              <th scope="col" title="Real observations">
                n
              </th>
              <th scope="col" title="Filled values">
                Filled
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map(({ area, state }) => {
              const s = state?.status === "done" ? describe(state.data.points) : null;
              const f = (x: number) => x.toFixed(axis.digits + 1);
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
