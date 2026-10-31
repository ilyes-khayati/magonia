import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Trend } from "../analyses";
import { trendOf, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { useAnalysis } from "../useAnalysis";
import Cautions from "./Cautions";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";
import { large } from "../variables";

type Props = {
  analysis: Trend;
  onChange: (change: Partial<Trend>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: Entry[]; // one per area
  options: (areaId: number) => SeriesOptions;
};

const TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" };
const TOOLTIP = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 };

// Annual means of each area with their Theil–Sen line, and the Mann–Kendall verdict
export default function TrendCard({ analysis, onChange, onRemove, variables, title, entries, options }: Props) {
  const variable = variables.find((v) => v.key === analysis.variable);
  const name = variable ? title(variable) : analysis.variable;
  const digits = large(analysis.variable) ? 2 : 3;

  const signature = JSON.stringify(entries.filter((e) => e.state?.status === "done").map((e) => options(e.area.id)));
  const requests = useMemo(
    () => (JSON.parse(signature) as SeriesOptions[]).map((o) => ({ key: JSON.stringify(o), body: o })),
    [signature],
  );
  const results = useAnalysis(requests, trendOf);
  const done = entries.flatMap((e) => {
    const r = results.get(JSON.stringify(options(e.area.id)));
    return r?.status === "done" ? [{ ...e, data: r.data }] : [];
  });

  // one row per year: each area's mean and its fitted line
  const rows = new Map<number, Record<string, number>>();
  for (const { area, data } of done) {
    const years = Object.keys(data.years).map(Number);
    const first = Math.min(...years);
    for (const y of years) {
      const row = rows.get(y) ?? { year: y };
      row[`m${area.id}`] = data.years[String(y)];
      if (data.slope !== null && data.intercept !== null) row[`t${area.id}`] = data.intercept + (data.slope / 10) * (y - first);
      rows.set(y, row);
    }
  }
  const chart = [...rows.values()].sort((a, b) => a.year - b.year);

  return (
    <section className="card" aria-label="Trend chart">
      <div className="card-head">
        <div>
          <h3>Long-term trend</h3>
          <span className="meta">Annual means, Theil–Sen slope and Mann–Kendall test</span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <label className="field">
        Variable
        <select className="select" value={analysis.variable} onChange={(e) => onChange({ variable: e.target.value as VariableKey })}>
          {variables.map((v) => (
            <option key={v.key} value={v.key}>
              {title(v)}
            </option>
          ))}
        </select>
      </label>

      {!done.length ? (
        <p className="placeholder">Waiting for the series to load.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chart} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="year" tick={TICK} />
              <YAxis tick={TICK} width={40} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(digits - 1)} />
              <Tooltip
                contentStyle={TOOLTIP}
                formatter={(value, key) => {
                  const area = entries.find((e) => e.area.id === Number(String(key).slice(1)))?.area.name ?? "";
                  return [Number(value).toFixed(digits), String(key).startsWith("t") ? `${area} trend` : `${area} ${name}`];
                }}
              />
              {done.map(({ area, colour }) => (
                <Line key={`m${area.id}`} dataKey={`m${area.id}`} stroke={colour} strokeWidth={1.4} dot={{ r: 2.5, fill: colour }} isAnimationActive={false} />
              ))}
              {done.map(({ area, colour }) => (
                <Line
                  key={`t${area.id}`}
                  dataKey={`t${area.id}`}
                  stroke={colour}
                  strokeWidth={2.4}
                  strokeDasharray="6 4"
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <div className="table-scroll" tabIndex={0}>
            <table className="stats models">
              <caption className="visually-hidden">Trend of each area</caption>
              <thead>
                <tr>
                  <th scope="col">Area</th>
                  <th scope="col">Per decade</th>
                  <th scope="col">p</th>
                  <th scope="col">Years</th>
                  <th scope="col">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {done.map(({ area, colour, data }) => (
                  <tr key={area.id}>
                    <th scope="row">
                      <span className="dot" style={{ background: colour }} /> {area.name}
                    </th>
                    <td>{data.slope === null ? "–" : `${data.slope >= 0 ? "+" : ""}${data.slope.toFixed(digits)}`}</td>
                    <td>{data.p === null ? "–" : data.p.toFixed(2)}</td>
                    <td>{Object.keys(data.years).length}</td>
                    <td>{data.p === null ? "–" : data.p < 0.05 ? "significant" : "could be chance"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="summary">
            {done.flatMap(({ data }) => data.summary).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <Cautions items={done.flatMap(({ data }) => data.cautions)} />
          <span className="meta">
            Each year is the mean of the months seen in most years, so missing winters do not bias it. Dashed: the
            Theil–Sen line.
          </span>
        </>
      )}
    </section>
  );
}
