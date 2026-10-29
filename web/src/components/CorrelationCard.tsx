import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Correlation } from "../analyses";
import type { Variable, VariableKey } from "../api";
import { correlationCautions, describeLink, lagCorrelation, type Lag } from "../correlation";
import type { Entry } from "./ChartCard";
import Cautions from "./Cautions";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Correlation;
  onChange: (change: Partial<Correlation>) => void;
  onRemove: () => void;
  variables: Variable[]; // the whole catalogue: an analysis fetches what it needs
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  seasonal: boolean; // seasonal means cannot be lagged by month
};

export default function CorrelationCard({ analysis, onChange, onRemove, variables, title, entries, seasonal }: Props) {
  const { response, driver, deseasonalise } = analysis;
  const name = (key: VariableKey) => {
    const variable = variables.find((v) => v.key === key);
    return variable ? title(variable) : key;
  };

  const drivers = entries(driver);
  const areas = entries(response).flatMap(({ area, colour, state }) => {
    const other = drivers.find((d) => d.area.id === area.id)?.state;
    if (state?.status !== "done" || other?.status !== "done") return [];
    return [
      {
        area,
        colour,
        lags: lagCorrelation(state.data.points, other.data.points, 12, deseasonalise),
        cautions: correlationCautions(area.name, name(response), name(driver), state.data.points, other.data.points, deseasonalise),
      },
    ];
  });

  // One row per lag, one column per area; the band is drawn for the area with the fewest months
  const data = Array.from({ length: 13 }, (_, lag) => {
    const row: Record<string, number> = { lag };
    for (const { area, lags } of areas) {
      const hit = lags.find((l: Lag) => l.lag === lag);
      if (hit) row[`r${area.id}`] = hit.r;
    }
    return row;
  });
  const band = Math.max(0, ...areas.flatMap((a) => a.lags.map((l) => l.band)));

  return (
    <section className="card" aria-label="Correlation chart">
      <div className="card-head">
        <div>
          <h3>Correlation</h3>
          <span className="meta">Monthly means · {name(driver)} leading {name(response)} by 0–12 months</span>
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
            style={{ width: "100%" }}
            value={response}
            onChange={(e) => {
              const next = e.target.value as VariableKey;
              // the driver must stay a different variable
              onChange({ response: next, driver: next === driver ? response : driver });
            }}
          >
            {variables.map((v) => (
              <option key={v.key} value={v.key}>
                {title(v)}
              </option>
            ))}
          </select>
        </label>
        <label className="field" style={{ minWidth: 0 }}>
          Driver
          <select
            className="select"
            style={{ width: "100%" }}
            value={driver}
            onChange={(e) => onChange({ driver: e.target.value as VariableKey })}
          >
            {variables
              .filter((v) => v.key !== response)
              .map((v) => (
                <option key={v.key} value={v.key}>
                  {title(v)}
                </option>
              ))}
          </select>
        </label>
        <label className="row" style={{ gap: 6, fontSize: 12, gridColumn: "1 / -1" }}>
          <input
            type="checkbox"
            checked={deseasonalise}
            onChange={(e) => onChange({ deseasonalise: e.target.checked })}
          />
          Remove seasonal cycle
        </label>
      </div>

      {seasonal ? (
        <p className="placeholder">Correlation needs native or monthly data. Change the time step on the left.</p>
      ) : !areas.length ? (
        <p className="placeholder">Waiting for both variables to load.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data} margin={{ top: 6, right: 6, bottom: 12, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <ReferenceArea y1={-band} y2={band} fill="var(--muted)" fillOpacity={0.12} stroke="none" />
              <ReferenceLine y={0} stroke="var(--zero)" />
              <XAxis
                dataKey="lag"
                tick={{ fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" }}
                label={{ value: "lag (months)", position: "insideBottom", offset: -10, fontSize: 10, fill: "var(--muted)" }}
              />
              <YAxis
                domain={[-1, 1]}
                ticks={[-1, -0.5, 0, 0.5, 1]}
                tick={{ fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" }}
                width={34}
              />
              <Tooltip
                contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 }}
                labelFormatter={(lag) => `${name(driver)} ${lag} month(s) earlier`}
                formatter={(value, key) => {
                  const id = Number(String(key).slice(1));
                  return [Number(value).toFixed(2), areas.find((a) => a.area.id === id)?.area.name ?? key];
                }}
              />
              {areas.map(({ area, colour }) => (
                <Line
                  key={area.id}
                  dataKey={`r${area.id}`}
                  stroke={colour}
                  strokeWidth={1.8}
                  dot={{ r: 2.5, fill: colour }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <ul className="summary">
            {areas.map(({ area, lags }) => (
              <li key={area.id}>{describeLink(area.name, name(response), name(driver), lags, deseasonalise)}</li>
            ))}
          </ul>
          <Cautions items={areas.flatMap((a) => a.cautions)} />
          <span className="meta">
            Grey band: correlations that could arise by chance (95%, ignoring autocorrelation, so a little
            optimistic).
            {!deseasonalise && " With the seasonal cycle kept, any two seasonal variables look correlated."}
          </span>
        </>
      )}
    </section>
  );
}
