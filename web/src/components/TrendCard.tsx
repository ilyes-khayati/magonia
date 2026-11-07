import CardTitle from "./CardTitle";
import { useMemo } from "react";
import type { Trend } from "../analyses";
import { trendOf, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { useAnalysis } from "../useAnalysis";
import Cautions from "./Cautions";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";
import { large } from "../variables";
import { TimeChart, type TimeSeries } from "../plot/Chart";
import { yLabel } from "../plot/series";
import { num, signed } from "../format";

type Props = {
  analysis: Trend;
  onChange: (change: Partial<Trend>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: Entry[]; // one per area
  options: (areaId: number) => SeriesOptions;
};

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

  // each area's annual means, and its fitted line dashed over them
  const year = (y: number) => new Date(Date.UTC(y, 6, 1));
  const chart: TimeSeries[] = done.flatMap(({ area, colour, data }) => {
    const years = Object.keys(data.years).map(Number).sort((a, b) => a - b);
    const first = years[0];
    const line = data.slope !== null && data.intercept !== null ? data : null;
    return [
      { id: `m${area.id}`, name: `${area.name} · annual mean`, colour, width: 1.2, dots: true, points: years.map((y) => ({ date: year(y), value: data.years[String(y)] })) },
      ...(line
        ? [{ id: `t${area.id}`, name: `${area.name} · Theil–Sen`, colour, width: 2, dashed: true, points: years.map((y) => ({ date: year(y), value: line.intercept! + (line.slope! / 10) * (y - first) })) }]
        : []),
    ];
  });

  return (
    <section className="card" aria-label="Trend chart">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Long-term trend" onRename={(name) => onChange({ name })} />
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
          <TimeChart title={`${name} trend`} series={chart} height={210} y={{ label: variable ? yLabel(variable) : name, digits: digits - 1 }} />
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
                    <td>{data.slope === null ? "–" : signed(data.slope, digits)}</td>
                    <td>{num(data.p, 2)}</td>
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
