import CardTitle from "./CardTitle";
import { useMemo, useState } from "react";
import * as Plot from "@observablehq/plot";
import { phenologyOf, type SeriesOptions } from "../api";
import { useAnalysis } from "../useAnalysis";
import Cautions from "./Cautions";
import { oneArea } from "../format";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";
import { TimeChart } from "../plot/Chart";
import { dateOf } from "../plot/time";

type Props = {
  name?: string;
  onRename?: (name: string | undefined) => void;
  onRemove: () => void;
  entries: Entry[]; // NDVI at its native step, one per area
  options: (areaId: number) => SeriesOptions;
};

// Each growing season's start, peak and end, marked on the smoothed NDVI of one area
export default function PhenologyCard({ name, onRename, onRemove, entries, options }: Props) {
  const signature = JSON.stringify(entries.filter((e) => e.state?.status === "done").map((e) => options(e.area.id)));
  const requests = useMemo(
    () => (JSON.parse(signature) as SeriesOptions[]).map((o) => ({ key: JSON.stringify(o), body: o })),
    [signature],
  );
  const results = useAnalysis(requests, phenologyOf);
  const found = entries.map((e) => ({ ...e, result: results.get(JSON.stringify(options(e.area.id))) }));
  const [picked, setPicked] = useState<number | null>(null);
  const shown = found.find((f) => f.area.id === picked) ?? found.find((f) => f.result?.status === "done") ?? found[0];
  const data = shown?.result?.status === "done" ? shown.result.data : null;
  const series = data && shown ? [{ id: "ndvi", name: "NDVI", colour: shown.colour, width: 1.5, points: data.smoothed.map((p) => ({ date: dateOf(p.date), value: p.value })) }] : [];
  const marks = (() => {
    if (!data) return [];
    const near = (date: string) => data.smoothed.reduce((a, b) => (Math.abs(+new Date(b.date) - +new Date(date)) < Math.abs(+new Date(a.date) - +new Date(date)) ? b : a));
    const at = (kind: "start" | "peak" | "end", colour: string, r: number) =>
      Plot.dot(
        data.seasons.map((s) => ({ date: dateOf(near(s[kind]).date), value: near(s[kind]).value })),
        { x: "date", y: "value", r, fill: colour, stroke: "var(--card)", strokeWidth: 1, clip: true },
      );
    return [at("start", "var(--accent)", 3), at("peak", "var(--ink)", 3.5), at("end", "var(--warning)", 3)];
  })();

  return (
    <section className="card" aria-label="Season dates chart">
      <div className="card-head">
        <div>
          <CardTitle name={name} fallback="Season dates" onRename={onRename} />
          <span className="meta">NDVI smoothed on 8-day steps · start and end at 20% of the climb to the peak</span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      {found.length > 1 && (
        <label className="field">
          Area
          <select className="select" value={shown?.area.id ?? ""} onChange={(e) => setPicked(Number(e.target.value))}>
            {found.map((f) => (
              <option key={f.area.id} value={f.area.id}>
                {f.area.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {shown?.result?.status === "failed" ? (
        <p className="placeholder">{shown.result.error}</p>
      ) : !data ? (
        <p className="placeholder">Waiting for the series to load.</p>
      ) : (
        <>
          <TimeChart title="Season dates" series={series} marks={marks} height={200} y={{ label: "NDVI", digits: 1 }} />
          <div className="legend">
            <span className="row" style={{ gap: 6 }}>
              <span className="dot" style={{ background: "var(--accent)" }} /> start
            </span>
            <span className="row" style={{ gap: 6 }}>
              <span className="dot" style={{ background: "var(--ink)" }} /> peak
            </span>
            <span className="row" style={{ gap: 6 }}>
              <span className="dot" style={{ background: "var(--warning)" }} /> end
            </span>
          </div>
          <div className="table-scroll" tabIndex={0}>
            <table className="stats models">
              <caption className="visually-hidden">Each growing season</caption>
              <thead>
                <tr>
                  <th scope="col">Peak year</th>
                  <th scope="col">Start</th>
                  <th scope="col">Peak</th>
                  <th scope="col">End</th>
                  <th scope="col">Days</th>
                  <th scope="col">Amplitude</th>
                </tr>
              </thead>
              <tbody>
                {data.seasons.map((s) => (
                  <tr key={s.year}>
                    <th scope="row">{s.year}</th>
                    <td>{s.start}</td>
                    <td>{s.peak}</td>
                    <td>{s.end}</td>
                    <td>{s.length}</td>
                    <td>{s.amplitude.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="summary">
            {oneArea(data.summary).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <Cautions items={data.cautions} />
        </>
      )}
    </section>
  );
}

// The chart's own date closest to a season date, so the marker sits on the line
