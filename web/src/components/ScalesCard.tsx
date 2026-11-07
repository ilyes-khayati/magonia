import * as Plot from "@observablehq/plot";
import { SPEI_SCALES, type Scales } from "../analyses";
import type { SeriesOptions, SeriesPoint, Variable, VariableKey } from "../api";
import { lagCorrelation, type Lag } from "../correlation";
import { num } from "../format";
import { PlotFrame } from "../plot/Chart";
import { seriesKey } from "../settings";
import { useSeries } from "../useSeries";
import type { Entry } from "./ChartCard";
import CardTitle from "./CardTitle";
import { CloseIcon } from "./Icons";

const SCALES = SPEI_SCALES;
const MAX_LAG = 6;

type Props = {
  analysis: Scales;
  onChange: (change: Partial<Scales>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean;
};

type Cell = Lag & { scale: number };

// Which SPEI accumulation, and how many months earlier, the response follows most closely: a
// grid of correlations instead of a scale picked by habit
export default function ScalesCard({ analysis, onChange, onRemove, variables, title, entries, options, seasonal }: Props) {
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  const areas = entries(analysis.response).map((e) => e.area);
  const areaId = areas.some((a) => a.id === analysis.area) ? analysis.area! : (areas[0]?.id ?? null);
  const area = areas.find((a) => a.id === areaId);
  const response = entries(analysis.response).find((e) => e.area.id === areaId)?.state;

  // the drought index at every scale, for this area, extracted like any other series
  const requests = area && !seasonal
    ? SCALES.map((scale) => {
        const o = { ...options(area.id, "spei"), scale };
        return { key: seriesKey(o, area.geometry), options: o, scale };
      })
    : [];
  const results = useSeries(requests);
  const done = requests.flatMap((r) => {
    const state = results.get(r.key);
    return state?.status === "done" ? [{ scale: r.scale, points: state.data.points as SeriesPoint[] }] : [];
  });

  const cells: Cell[] =
    response?.status === "done"
      ? done.flatMap(({ scale, points }) =>
          lagCorrelation(response.data.points, points, MAX_LAG, analysis.deseasonalise).map((l) => ({ ...l, scale })),
        )
      : [];
  const best = cells.length ? cells.reduce((a, b) => (Math.abs(b.r) > Math.abs(a.r) ? b : a)) : null;
  const limit = Math.max(0.3, ...cells.map((c) => Math.abs(c.r)));

  const chart: Plot.PlotOptions = {
    marginLeft: 64,
    marginBottom: 40,
    x: { domain: Array.from({ length: MAX_LAG + 1 }, (_, i) => i), label: "Months earlier", labelAnchor: "center", labelArrow: "none", labelOffset: 34, tickSize: 0 },
    y: { domain: SCALES, label: null, tickFormat: (s: number) => `SPEI-${s}`, tickSize: 0 },
    color: { type: "diverging", scheme: "RdBu", domain: [-limit, limit] },
    marks: [
      Plot.cell(cells, { x: "lag", y: "scale", fill: "r", inset: 0.5 }),
      Plot.text(cells, {
        x: "lag",
        y: "scale",
        text: (c: Cell) => num(c.r, 2),
        fill: (c: Cell) => (Math.abs(c.r) > limit * 0.6 ? "white" : "black"),
        fontSize: 10,
        // a value inside the band of chance is shown faint
        fillOpacity: (c: Cell) => (Math.abs(c.r) < c.band ? 0.45 : 1),
      }),
      ...(best ? [Plot.cell([best], { x: "lag", y: "scale", stroke: "currentColor", strokeWidth: 2, fill: "none", inset: 0.5 })] : []),
      Plot.tip(cells, Plot.pointer({ x: "lag", y: "scale", title: (c: Cell) => `SPEI-${c.scale}, ${c.lag} month${c.lag === 1 ? "" : "s"} earlier\nr = ${num(c.r, 2)} (n = ${c.n}, chance ±${num(c.band, 2)})` })),
    ],
  };

  const waiting = !!area && done.length < SCALES.length;

  return (
    <section className="card" aria-label="Drought scale chart">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Drought scale and lag" onRename={(n) => onChange({ name: n })} />
          <span className="meta">
            {name(analysis.response)} {analysis.deseasonalise ? "anomalies" : "values"} against SPEI at {SCALES.length} accumulation scales and lags 0 to {MAX_LAG}
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <div className="drivers">
        <label className="field">
          Response
          <select className="select" value={analysis.response} onChange={(e) => onChange({ response: e.target.value as VariableKey })}>
            {variables
              .filter((v) => v.key !== "spei")
              .map((v) => (
                <option key={v.key} value={v.key}>
                  {title(v)}
                </option>
              ))}
          </select>
        </label>
        {areas.length > 1 && (
          <label className="field">
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
        <label className="row" style={{ gap: 6, fontSize: 12, gridColumn: "1 / -1" }}>
          <input type="checkbox" checked={analysis.deseasonalise} onChange={(e) => onChange({ deseasonalise: e.target.checked })} />
          Remove seasonal cycle
        </label>
      </div>

      {seasonal ? (
        <p className="placeholder">Lags are in months. Change the time step on the left to native or monthly.</p>
      ) : !area || response?.status !== "done" ? (
        <p className="placeholder">Waiting for {name(analysis.response)} to load.</p>
      ) : (
        <>
          <PlotFrame title="Drought scale and lag" options={chart} height={260} />
          {waiting && (
            <p className="meta" role="status">
              Extracting SPEI at {SCALES.length - done.length} more scale{SCALES.length - done.length === 1 ? "" : "s"}…
            </p>
          )}
          {best && (
            <ul className="summary">
              <li>
                {name(analysis.response)} {analysis.deseasonalise ? "anomalies" : "values"} follow SPEI-{best.scale} from{" "}
                {best.lag === 0 ? "the same month" : `${best.lag} month${best.lag === 1 ? "" : "s"} earlier`} most closely (r ={" "}
                {num(best.r, 2)}, {best.n} months, chance ±{num(best.band, 2)})
                {Math.abs(best.r) < best.band ? "; this does not stand out from chance." : "."}
              </li>
            </ul>
          )}
          <span className="meta">
            Picking the best of {SCALES.length * (MAX_LAG + 1)} cells favours a high value by chance: read the outlined cell as a
            lead to test, not a result. Faint numbers lie inside the band of chance.
          </span>
        </>
      )}
    </section>
  );
}
