import CardTitle from "./CardTitle";
import * as Plot from "@observablehq/plot";
import type { Correlation } from "../analyses";
import type { SeriesOptions, Variable, VariableKey } from "../api";
import ComponentCorrelation from "./ComponentCorrelation";
import { correlationCautions, describeLink, lagCorrelation, type Lag } from "../correlation";
import type { Entry } from "./ChartCard";
import Cautions from "./Cautions";
import { CloseIcon } from "./Icons";
import { PlotFrame } from "../plot/Chart";
import { num } from "../format";

type Props = {
  analysis: Correlation;
  onChange: (change: Partial<Correlation>) => void;
  onRemove: () => void;
  variables: Variable[]; // the whole catalogue: an analysis fetches what it needs
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  seasonal: boolean; // seasonal means cannot be lagged by month
  native: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
};

export default function CorrelationCard({ analysis, onChange, onRemove, variables, title, entries, seasonal, native, options }: Props) {
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

  const rows = areas.flatMap(({ area, colour, lags }) => lags.map((l: Lag) => ({ ...l, area: area.name, colour })))
  const band = Math.max(0, ...areas.flatMap((a) => a.lags.map((l) => l.band)));
  const chart: Plot.PlotOptions = {
    marginBottom: 40,
    x: { domain: [-0.5, 12.5], ticks: 13, label: "Lag (months)", labelAnchor: "center", labelArrow: "none", labelOffset: 34, tickSize: 4 },
    y: { domain: [-1, 1], ticks: [-1, -0.5, 0, 0.5, 1], grid: true, label: "r", labelArrow: "none", tickFormat: (v: number) => num(v, 1), tickSize: 0 },
    marks: [
      Plot.rect([{}], { y1: -band, y2: band, fill: "currentColor", fillOpacity: 0.07 }),
      Plot.ruleY([0], { stroke: "currentColor", strokeOpacity: 0.45 }),
      Plot.lineY(rows, { x: "lag", y: "r", z: "area", stroke: "colour", strokeWidth: 1.6 }),
      Plot.dot(rows, { x: "lag", y: "r", fill: "colour", r: 2.4 }),
      Plot.tip(rows, Plot.pointer({ x: "lag", y: "r", title: (l: Lag & { area: string }) => `${l.area}: ${name(driver)} ${l.lag} month${l.lag === 1 ? "" : "s"} earlier\nr = ${num(l.r, 2)} (n = ${l.n})` })),
    ],
  };

  return (
    <section className="card" aria-label="Correlation chart">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Correlation" onRename={(name) => onChange({ name })} />
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
        <label className="row" style={{ gap: 6, fontSize: 12, gridColumn: "1 / -1" }}>
          <input
            type="checkbox"
            checked={analysis.components ?? false}
            onChange={(e) => onChange({ components: e.target.checked })}
          />
          Also correlate trend and seasonal parts separately
        </label>
      </div>

      {seasonal ? (
        <p className="placeholder">Correlation needs native or monthly data. Change the time step on the left.</p>
      ) : !areas.length ? (
        <p className="placeholder">Waiting for both variables to load.</p>
      ) : (
        <>
          <PlotFrame title="Lag correlation" options={chart} height={200} />
          {analysis.components && (
            <ComponentCorrelation response={response} driver={driver} name={name} native={native} options={options} />
          )}
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
