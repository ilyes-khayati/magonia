import CardTitle from "./CardTitle";
import { useMemo } from "react";
import * as Plot from "@observablehq/plot";
import type { Lags } from "../analyses";
import { exploreLags, type LagsBody, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { areaColour, type Theme } from "../theme";
import { useAnalysis } from "../useAnalysis";
import type { Entry } from "./ChartCard";
import Cautions from "./Cautions";
import { CloseIcon } from "./Icons";
import { PlotFrame } from "../plot/Chart";
import { num, oneArea } from "../format";

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

  const memory = useMemo(() => found?.acf.map((r, i) => ({ lag: i + 1, r, out: Math.abs(r) > found.acf_band })) ?? [], [found]);
  // each driver's r divided by its own bound, so that beyond ±1 stands out for all of them
  const links = Array.from({ length: 12 }, (_, i) => {
    const row: Record<string, number> = { lag: i + 1 };
    found?.drivers.forEach((d, j) => (row[`d${j}`] = d.r[i] / d.bound));
    return row;
  });
  // whole-number ticks that always include the ±1 bounds, so a line can be seen to cross one
  const ratios = links.flatMap((row) => Object.entries(row).filter(([k]) => k !== "lag").map(([, v]) => v));
  const low = Math.min(-1, Math.floor(Math.min(...ratios.filter(Number.isFinite))));
  const high = Math.max(1, Math.ceil(Math.max(...ratios.filter(Number.isFinite))));
  const band = found?.acf_band ?? 0;
  const memoryChart = useMemo<Plot.PlotOptions>(
    () => ({
      marginBottom: 40,
      x: { label: "Months earlier", labelAnchor: "center", labelArrow: "none", labelOffset: 34, tickSize: 0, padding: 0.25 },
      y: { domain: [-1, 1], ticks: [-1, -0.5, 0, 0.5, 1], grid: true, label: "r", labelArrow: "none", tickFormat: (v: number) => num(v, 1), tickSize: 0 },
      marks: [
        Plot.rect([{}], { y1: -band, y2: band, fill: "currentColor", fillOpacity: 0.07 }),
        Plot.barY(memory, { x: "lag", y: "r", fill: (m: { out: boolean }) => (m.out ? "var(--accent)" : "var(--zero)"), className: "lag-bar" }),
        Plot.ruleY([0], { stroke: "currentColor", strokeOpacity: 0.45 }),
        Plot.tip(memory, Plot.pointerX({ x: "lag", y: "r", title: (m: { lag: number; r: number }) => `${m.lag} month${m.lag > 1 ? "s" : ""} earlier\nr = ${num(m.r, 2)}` })),
      ],
    }),
    [memory, band],
  );
  const linksChart = useMemo<Plot.PlotOptions>(() => {
    const driverRows = (found?.drivers ?? []).flatMap((d, j) =>
      d.r.slice(0, 12).map((r, i) => ({ lag: i + 1, ratio: r / d.bound, r, driver: d.driver, colour: areaColour(theme, j + 2) })),
    );
    const ratioTicks = Array.from({ length: high - low + 1 }, (_, i) => low + i);
    return {
      marginBottom: 40,
      x: { domain: [0.5, 12.5], ticks: 12, label: "Months earlier", labelAnchor: "center", labelArrow: "none", labelOffset: 34, tickSize: 4 },
      y: { domain: [low, high], ticks: ratioTicks, grid: true, label: "r ÷ bound", labelArrow: "none", tickFormat: (v: number) => num(v, 0), tickSize: 0 },
      marks: [
        Plot.rect([{}], { y1: -1, y2: 1, fill: "currentColor", fillOpacity: 0.07 }),
        Plot.ruleY([0], { stroke: "currentColor", strokeOpacity: 0.45 }),
        Plot.lineY(driverRows, { x: "lag", y: "ratio", z: "driver", stroke: "colour", strokeWidth: 1.6 }),
        Plot.dot(driverRows, { x: "lag", y: "ratio", fill: "colour", r: 2.4 }),
        Plot.tip(driverRows, Plot.pointer({ x: "lag", y: "ratio", title: (d: { lag: number; r: number; ratio: number; driver: string }) => `${d.driver}, ${d.lag} month${d.lag > 1 ? "s" : ""} earlier\nr = ${num(d.r, 2)} (×${num(d.ratio, 1)} the bound)` })),
      ],
    };
  }, [found, low, high, theme]);

  return (
    <section className="card" aria-label="Lags chart">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Memory and lags" onRename={(name) => onChange({ name })} />
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
            Memory: {name(analysis.response)} against itself, 1 to 24 months earlier (highlighted bars stand out from chance)
          </span>
          <PlotFrame title="Memory" options={memoryChart} height={150} />

          {found.drivers.length > 0 && (
            <>
              <span className="meta">
                Drivers: correlation divided by its bound, which allows for autocorrelation and for picking the best of
                12 lags; beyond ±1 stands out
              </span>
              <PlotFrame title="Drivers" options={linksChart} height={170} />
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
            {oneArea(found.summary).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <Cautions items={found.cautions} />
          <span className="meta">
            As anomalies, part of a driver&apos;s link can run through {name(analysis.response)}&apos;s own memory. A
            forecast experiment on the Model page, with both as predictors, tells them apart.
          </span>
        </>
      )}
    </section>
  );
}
