import CardTitle from "./CardTitle";
import { useMemo } from "react";
import type { Decomposition } from "../analyses";
import { decomposeSeries, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { useAnalysis } from "../useAnalysis";
import type { Entry } from "./ChartCard";
import Cautions from "./Cautions";
import { CloseIcon } from "./Icons";
import { large } from "../variables";
import { TimeChart, type TimeSeries } from "../plot/Chart";
import { dateOf } from "../plot/time";
import { yLabel } from "../plot/series";

type Props = {
  analysis: Decomposition;
  onChange: (change: Partial<Decomposition>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: Entry[]; // the variable at its native time step, one per area
  options: (areaId: number) => SeriesOptions; // the request behind each entry
};


export default function DecompositionCard({ analysis, onChange, onRemove, variables, title, entries, options }: Props) {
  const variable = variables.find((v) => v.key === analysis.variable);
  const name = variable ? title(variable) : analysis.variable;
  const digits = large(analysis.variable) ? 1 : 2;

  // a decomposition is asked for once the series behind it has been extracted
  const signature = JSON.stringify(entries.filter((e) => e.state?.status === "done").map((e) => options(e.area.id)));
  const requests = useMemo(
    () => (JSON.parse(signature) as SeriesOptions[]).map((o) => ({ key: JSON.stringify(o), body: o })),
    [signature],
  );
  const results = useAnalysis(requests, decomposeSeries);
  const parts = entries.map((e) => ({ ...e, result: results.get(JSON.stringify(options(e.area.id))) }));
  const done = parts.flatMap((p) => (p.result?.status === "done" ? [{ ...p, data: p.result.data }] : []));

  // each area's value faint under its trend, and its seasonal part below
  const whole: TimeSeries[] = done.flatMap(({ area, colour, data }) => [
    { id: `v${area.id}`, name: `${area.name} · value`, colour, width: 1, opacity: 0.35, points: data.points.map((p) => ({ date: dateOf(p.date), value: p.value })) },
    { id: `t${area.id}`, name: `${area.name} · trend`, colour, width: 2.2, points: data.points.map((p) => ({ date: dateOf(p.date), value: p.trend })) },
  ]);
  const season: TimeSeries[] = done.map(({ area, colour, data }) => ({
    id: `s${area.id}`,
    name: `${area.name} · seasonal`,
    colour,
    width: 1.3,
    points: data.points.map((p) => ({ date: dateOf(p.date), value: p.seasonal })),
  }));
  const method = done[0]?.data;

  return (
    <section className="card" aria-label="Decomposition chart">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Trend and season" onRename={(name) => onChange({ name })} />
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
          <TimeChart title={`${name} and its trend`} series={whole} height={190} y={{ label: variable ? yLabel(variable) : name, digits }} />

          <span className="meta">Seasonal part (the series minus its trend)</span>
          <TimeChart title={`${name} seasonal part`} series={season} height={130} y={{ label: "Seasonal part", digits, zero: true }} />
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
      <Cautions items={parts.flatMap(({ result }) => (result?.status === "done" ? (result.data.cautions ?? []) : []))} />
      {method && (
        <span className="meta">
          The wavelet uses later data too, so the trend describes the past and is not a forecast.
          {method.interpolated > 0 && ` ${method.interpolated} empty dates were filled by straight lines first.`}
        </span>
      )}
    </section>
  );
}
