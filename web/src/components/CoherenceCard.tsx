import * as Plot from "@observablehq/plot";
import type { Coherence } from "../analyses";
import { coherenceOf, type CoherenceBody, type CoherenceResponse, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { oneArea } from "../format";
import { PlotFrame } from "../plot/Chart";
import { dateOf } from "../plot/time";
import { useAnalysis } from "../useAnalysis";
import type { Entry } from "./ChartCard";
import CardTitle from "./CardTitle";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Coherence;
  onChange: (change: Partial<Coherence>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean;
};

const TICKS = [2, 3, 6, 12, 24, 48, 96];
const RAMP = ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"];

const nextMonth = (d: Date) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));

// The coherence map as Plot marks: a cell per month and period, a line around what beats red
// noise, the ends of the record shaded where the transform is distorted, and phase arrows
function marks(found: CoherenceResponse) {
  const times = found.times.map((t) => dateOf(`${t}-01`));
  const n = found.periods.length;
  // each period's band spans halfway, in log terms, to its neighbours
  const edges = found.periods.map((p, i) => {
    const below = i > 0 ? Math.sqrt(p * found.periods[i - 1]) : p / Math.sqrt(found.periods[1] / p);
    const above = i < n - 1 ? Math.sqrt(p * found.periods[i + 1]) : p * Math.sqrt(p / found.periods[n - 2]);
    return [below, above];
  });
  const cells = found.coherence.flatMap((row, i) =>
    row.map((value, j) => ({ x1: times[j], x2: nextMonth(times[j]), y1: edges[i][0], y2: edges[i][1], value })),
  );
  // the outline of the significant region, edge by edge
  const sig = found.significant;
  const outline: { x1: Date; x2: Date; y1: number; y2: number }[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < times.length; j++) {
      if (!sig[i][j]) continue;
      if (i === 0 || !sig[i - 1][j]) outline.push({ x1: times[j], x2: nextMonth(times[j]), y1: edges[i][0], y2: edges[i][0] });
      if (i === n - 1 || !sig[i + 1][j]) outline.push({ x1: times[j], x2: nextMonth(times[j]), y1: edges[i][1], y2: edges[i][1] });
      if (j === 0 || !sig[i][j - 1]) outline.push({ x1: times[j], x2: times[j], y1: edges[i][0], y2: edges[i][1] });
      if (j === times.length - 1 || !sig[i][j + 1]) outline.push({ x1: nextMonth(times[j]), x2: nextMonth(times[j]), y1: edges[i][0], y2: edges[i][1] });
    }
  }
  const top = edges[n - 1][1];
  const cone = times.map((t, j) => ({ t, coi: Math.min(Math.max(found.coi[j], edges[0][0]), top) }));
  // arrows every six months and about every half octave, where coherence is strong and real
  const arrows = [];
  for (let i = 2; i < n; i += 4) {
    for (let j = 3; j < times.length; j += 6) {
      if (sig[i][j] && found.coherence[i][j] > 0.5 && found.periods[i] <= found.coi[j]) {
        arrows.push({ x: times[j], y: found.periods[i], rotate: 90 + (found.phase[i][j] * 180) / Math.PI });
      }
    }
  }
  return [
    Plot.rect(cells, { x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: "value" }),
    Plot.areaY(cone, { x: "t", y1: "coi", y2: top, fill: "var(--card)", fillOpacity: 0.6, curve: "step" }),
    Plot.link(outline, { x1: "x1", x2: "x2", y1: "y1", y2: "y2", stroke: "black", strokeWidth: 1 }),
    Plot.vector(arrows, { x: "x", y: "y", rotate: "rotate", length: 9, stroke: "black", strokeWidth: 1.2, anchor: "middle" }),
  ];
}

// When, and at which periods, two variables move together, and which one leads
export default function CoherenceCard({ analysis, onChange, onRemove, variables, title, entries, options, seasonal }: Props) {
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  const areas = entries(analysis.response)
    .filter((e) => entries(analysis.driver).some((d) => d.area.id === e.area.id))
    .map((e) => e.area);
  const areaId = areas.some((a) => a.id === analysis.area) ? analysis.area! : (areas[0]?.id ?? null);
  const done = (key: VariableKey) => entries(key).find((e) => e.area.id === areaId)?.state?.status === "done";
  const body: CoherenceBody | null =
    areaId !== null && !seasonal && done(analysis.response) && done(analysis.driver)
      ? { response: options(areaId, analysis.response), driver: options(areaId, analysis.driver), deseasonalise: analysis.deseasonalise }
      : null;
  const signature = JSON.stringify(body);
  const requests = signature === "null" ? [] : [{ key: signature, body: JSON.parse(signature) as CoherenceBody }];
  const result = useAnalysis(requests, coherenceOf).get(signature);
  const found = result?.status === "done" ? result.data : null;

  const chart: Plot.PlotOptions | null = found && {
    marginLeft: 48,
    x: { type: "utc", label: null, tickSize: 4, ticks: 8 },
    y: { type: "log", domain: [found.periods[0], found.periods[found.periods.length - 1]], ticks: TICKS, tickFormat: (p: number) => `${p}`, label: "Period (months)", labelArrow: "none", reverse: true },
    color: { domain: [0, 1], range: RAMP, interpolate: "rgb" },
    marks: marks(found),
  };

  return (
    <section className="card" aria-label="Coherence chart">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Wavelet coherence" onRename={(n) => onChange({ name: n })} />
          <span className="meta">
            {name(analysis.response)} and {name(analysis.driver)}, month by month and period by period (Morlet wavelet, Grinsted coherence, 95% against red noise)
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <div className="drivers">
        <label className="field">
          First
          <select className="select" value={analysis.response} onChange={(e) => onChange({ response: e.target.value as VariableKey })}>
            {variables.map((v) => (
              <option key={v.key} value={v.key}>
                {title(v)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Second
          <select className="select" value={analysis.driver} onChange={(e) => onChange({ driver: e.target.value as VariableKey })}>
            {variables
              .filter((v) => v.key !== analysis.response)
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
          Remove seasonal cycle first
        </label>
      </div>

      {seasonal ? (
        <p className="placeholder">Coherence needs monthly values. Change the time step on the left to native or monthly.</p>
      ) : result?.status === "failed" ? (
        <p className="placeholder">{result.error}</p>
      ) : !found || !chart ? (
        <p className="placeholder" role="status">
          {body ? "Computing coherence and its significance against red noise…" : `Waiting for ${name(analysis.response)} and ${name(analysis.driver)} to load.`}
        </p>
      ) : (
        <>
          <PlotFrame title="Wavelet coherence" options={chart} height={280} />
          <div className="coherence-key">
            <span className="ramp" style={{ background: `linear-gradient(to right, ${RAMP.join(", ")})` }} />
            <span className="meta">0 → 1 coherence</span>
            <span className="meta">
              Outlined: beyond red noise (95%). Pale ends: distorted by the record&apos;s edges. Arrows: → together, ← opposite,
              ↓ {name(analysis.response)} leads, ↑ {name(analysis.driver)} leads.
            </span>
          </div>
          <ul className="summary">
            {oneArea(found.summary).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
