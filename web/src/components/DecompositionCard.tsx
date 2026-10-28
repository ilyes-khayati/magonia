import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Decomposition } from "../analyses";
import type { SeriesOptions, Variable, VariableKey } from "../api";
import { useDecomposition } from "../useDecomposition";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Decomposition;
  onChange: (change: Partial<Decomposition>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: Entry[]; // the variable at its native time step, one per area
  options: (areaId: number) => SeriesOptions; // the request behind each entry
};

type Row = Record<string, string | number | null>;

const TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" };
const TOOLTIP = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 };

export default function DecompositionCard({ analysis, onChange, onRemove, variables, title, entries, options }: Props) {
  const variable = variables.find((v) => v.key === analysis.variable);
  const name = variable ? title(variable) : analysis.variable;
  const digits = analysis.variable === "lst" ? 1 : 2;

  // a decomposition is asked for once the series behind it has been extracted
  const signature = JSON.stringify(entries.filter((e) => e.state?.status === "done").map((e) => options(e.area.id)));
  const requests = useMemo(
    () => (JSON.parse(signature) as SeriesOptions[]).map((o) => ({ key: JSON.stringify(o), options: o })),
    [signature],
  );
  const results = useDecomposition(requests);
  const parts = entries.map((e) => ({ ...e, result: results.get(JSON.stringify(options(e.area.id))) }));
  const done = parts.flatMap((p) => (p.result?.status === "done" ? [{ ...p, data: p.result.data }] : []));

  // one row per month, with the value, trend and seasonal part of each area
  const table = new Map<string, Row>();
  for (const { area, data } of done) {
    for (const p of data.points) {
      const row = table.get(p.date) ?? { date: p.date };
      row[`v${area.id}`] = p.value;
      row[`t${area.id}`] = p.trend;
      row[`s${area.id}`] = p.seasonal;
      table.set(p.date, row);
    }
  }
  const data = [...table.values()].sort((a, b) => (String(a.date) < String(b.date) ? -1 : 1));
  const method = done[0]?.data;
  const areaName = (key: string) => entries.find((e) => e.area.id === Number(key.slice(1)))?.area.name ?? key;

  return (
    <section className="card" aria-label="Decomposition chart">
      <div className="card-head">
        <div>
          <h3>Trend and season</h3>
          <span className="meta">
            {method
              ? `Discrete Meyer wavelet, level ${method.level} on ${Math.round(method.cadence_days)}-day steps · trend keeps cycles longer than ~${Math.round(method.semi_period_days)} days`
              : "Discrete Meyer wavelet at the product's own time step"}
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <label className="field">
        Variable
        <select
          className="select"
          value={analysis.variable}
          onChange={(e) => onChange({ variable: e.target.value as VariableKey })}
        >
          {variables.map((v) => (
            <option key={v.key} value={v.key}>
              {title(v)}
            </option>
          ))}
        </select>
      </label>

      {!done.length ? (
        <p className="placeholder">
          {parts.some((p) => p.result?.status === "failed" || p.state?.status === "failed")
            ? "This series could not be decomposed; see below."
            : `Extracting ${name} at its own time step, then decomposing it…`}
        </p>
      ) : (
        <>
          <span className="meta">{name} and its trend</span>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tick={TICK} tickFormatter={(d: string) => d.slice(0, 4)} minTickGap={36} />
              <YAxis tick={TICK} width={38} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(digits)} />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(d) => String(d).slice(0, 7)}
                formatter={(value, key) => [
                  Number(value).toFixed(digits + 1),
                  `${areaName(String(key))} ${String(key)[0] === "t" ? "trend" : name}`,
                ]}
              />
              {done.map(({ area, colour }) => (
                <Line
                  key={`v${area.id}`}
                  dataKey={`v${area.id}`}
                  stroke={colour}
                  strokeOpacity={0.35}
                  strokeWidth={1}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
              {done.map(({ area, colour }) => (
                <Line
                  key={`t${area.id}`}
                  dataKey={`t${area.id}`}
                  stroke={colour}
                  strokeWidth={2.4}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          <span className="meta">Seasonal part (the series minus its trend)</span>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tick={TICK} tickFormatter={(d: string) => d.slice(0, 4)} minTickGap={36} />
              <YAxis tick={TICK} width={38} tickFormatter={(v) => Number(v).toFixed(digits)} />
              <ReferenceLine y={0} stroke="var(--zero)" />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(d) => String(d).slice(0, 7)}
                formatter={(value, key) => [Number(value).toFixed(digits + 1), `${areaName(String(key))} seasonal`]}
              />
              {done.map(({ area, colour }) => (
                <Line
                  key={`s${area.id}`}
                  dataKey={`s${area.id}`}
                  stroke={colour}
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
        {parts.map(({ area, result, state }) =>
          state?.status === "failed" ? (
            <li key={area.id}>
              {area.name}: {state.error}
            </li>
          ) : result?.status === "failed" ? (
            <li key={area.id}>
              {area.name}: {result.error}
            </li>
          ) : result?.status === "done" ? (
            result.data.summary.slice(0, 2).map((line) => <li key={line}>{line}</li>)
          ) : null,
        )}
      </ul>
      {method && (
        <span className="meta">
          The wavelet uses later data too, so the trend describes the past and is not a forecast.
          {method.interpolated > 0 && ` ${method.interpolated} empty dates were filled by straight lines first.`}
        </span>
      )}
    </section>
  );
}
