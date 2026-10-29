import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Lags } from "../analyses";
import { exploreLags, type LagsBody, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { areaColour, type Theme } from "../theme";
import { useAnalysis } from "../useAnalysis";
import type { Entry } from "./ChartCard";
import Cautions from "./Cautions";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Lags;
  onChange: (change: Partial<Lags>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean; // seasonal means cannot be lagged by month
};

const TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" };
const TOOLTIP = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 };

export default function LagsCard(props: Props) {
  const { analysis, onChange, onRemove, variables, title, entries, options, seasonal } = props;
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  const areas = entries(analysis.response).map((e) => e.area);
  const areaId = areas.some((a) => a.id === analysis.area) ? analysis.area! : (areas[0]?.id ?? null);
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";

  // asked for once the response and every driver of this area have been extracted
  const done = (key: VariableKey) =>
    entries(key).find((e) => e.area.id === areaId)?.state?.status === "done";
  const ready = areaId !== null && !seasonal && [analysis.response, ...analysis.drivers].every(done);
  const body: LagsBody | null = ready
    ? {
        response: options(areaId, analysis.response),
        drivers: analysis.drivers.map((k) => options(areaId, k)),
        deseasonalise: analysis.deseasonalise,
      }
    : null;
  const signature = JSON.stringify(body);
  const requests = useMemo(
    () => (signature === "null" ? [] : [{ key: signature, body: JSON.parse(signature) as LagsBody }]),
    [signature],
  );
  const result = useAnalysis(requests, exploreLags).get(signature);
  const found = result?.status === "done" ? result.data : null;

  const memory = found?.acf.map((r, i) => ({ lag: i + 1, r, out: Math.abs(r) > found.acf_band })) ?? [];
  // each driver's r divided by its own bound, so that beyond ±1 stands out for all of them
  const links = Array.from({ length: 12 }, (_, i) => {
    const row: Record<string, number> = { lag: i + 1 };
    found?.drivers.forEach((d, j) => (row[`d${j}`] = d.r[i] / d.bound));
    return row;
  });

  return (
    <section className="card" aria-label="Lags chart">
      <div className="card-head">
        <div>
          <h3>Memory and lags</h3>
          <span className="meta">
            {name(analysis.response)} {analysis.deseasonalise ? "anomalies" : "values"} against their own past and
            their drivers&apos;, 1 to 12 months earlier
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <label className="field" style={{ minWidth: 0 }}>
          Response
          <select
            className="select"
            value={analysis.response}
            onChange={(e) => {
              const response = e.target.value as VariableKey;
              onChange({ response, drivers: analysis.drivers.filter((k) => k !== response) });
            }}
          >
            {variables.map((v) => (
              <option key={v.key} value={v.key}>
                {title(v)}
              </option>
            ))}
          </select>
        </label>
        {areas.length > 1 && (
          <label className="field" style={{ minWidth: 0 }}>
            Area
            <select className="select" value={areaId ?? ""} onChange={(e) => onChange({ area: Number(e.target.value) })}>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <fieldset className="drivers" style={{ gridColumn: "1 / -1" }}>
          <legend>Drivers</legend>
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
          <label className="row" style={{ gap: 6, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={analysis.deseasonalise}
              onChange={(e) => onChange({ deseasonalise: e.target.checked })}
            />
            Remove seasonal cycle
          </label>
        </fieldset>
      </div>

      {seasonal ? (
        <p className="placeholder">Lags are in months. Change the time step on the left to native or monthly.</p>
      ) : result?.status === "failed" ? (
        <p className="placeholder">{result.error}</p>
      ) : !found ? (
        <p className="placeholder">Waiting for the series to load.</p>
      ) : (
        <>
          <span className="meta">
            Memory: {name(analysis.response)} against itself, 1 to 24 months earlier (dark bars stand out from chance)
          </span>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={memory} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <ReferenceArea y1={-found.acf_band} y2={found.acf_band} fill="var(--muted)" fillOpacity={0.12} stroke="none" />
              <ReferenceLine y={0} stroke="var(--zero)" />
              <XAxis dataKey="lag" tick={TICK} interval={1} />
              <YAxis domain={[-1, 1]} ticks={[-1, 0, 1]} tick={TICK} width={30} />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(lag) => `${lag} month(s) earlier`}
                formatter={(value) => [Number(value).toFixed(2), "r"]}
              />
              <Bar dataKey="r" isAnimationActive={false}>
                {memory.map((m) => (
                  <Cell key={m.lag} fill={m.out ? "var(--accent)" : "var(--zero)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {found.drivers.length > 0 && (
            <>
              <span className="meta">
                Drivers: correlation divided by its bound, which allows for autocorrelation and for picking the best of
                12 lags; beyond ±1 stands out
              </span>
              <ResponsiveContainer width="100%" height={150}>
                <LineChart data={links} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <ReferenceArea y1={-1} y2={1} fill="var(--muted)" fillOpacity={0.12} stroke="none" />
                  <ReferenceLine y={0} stroke="var(--zero)" />
                  <XAxis dataKey="lag" tick={TICK} />
                  <YAxis tick={TICK} width={30} />
                  <Tooltip
                    contentStyle={TOOLTIP}
                    labelFormatter={(lag) => `${lag} month(s) earlier`}
                    formatter={(value, key) => {
                      const d = found.drivers[Number(String(key).slice(1))];
                      return [`${(Number(value) * d.bound).toFixed(2)} (×${Number(value).toFixed(1)} the bound)`, d.driver];
                    }}
                  />
                  {found.drivers.map((d, j) => (
                    <Line
                      key={d.driver}
                      dataKey={`d${j}`}
                      stroke={areaColour(theme, j + 2)}
                      strokeWidth={1.8}
                      dot={{ r: 2.5 }}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              <div className="legend">
                {found.drivers.map((d, j) => (
                  <span key={d.driver} className="row" style={{ gap: 6 }}>
                    <span className="dot" style={{ background: areaColour(theme, j + 2) }} />
                    {d.driver}: {d.decision}
                  </span>
                ))}
              </div>
            </>
          )}
          <ul className="summary">
            {found.summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <Cautions items={found.cautions} />
          <span className="meta">
            As anomalies, part of a driver&apos;s link can run through {name(analysis.response)}&apos;s own memory. The paper
            also removes that memory first; that comes with the models.
          </span>
        </>
      )}
    </section>
  );
}
