import CardTitle from "./CardTitle";
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { phenologyOf, type SeriesOptions } from "../api";
import { useAnalysis } from "../useAnalysis";
import Cautions from "./Cautions";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";

type Props = {
  name?: string;
  onRename?: (name: string | undefined) => void;
  onRemove: () => void;
  entries: Entry[]; // NDVI at its native step, one per area
  options: (areaId: number) => SeriesOptions;
};

const TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" };
const TOOLTIP = { background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8 };

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
  const value = (date: string) => data?.smoothed.reduce((a, b) => (Math.abs(+new Date(b.date) - +new Date(date)) < Math.abs(+new Date(a.date) - +new Date(date)) ? b : a)).value;

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
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data.smoothed} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tick={TICK} tickFormatter={(d: string) => d.slice(0, 4)} minTickGap={40} />
              <YAxis tick={TICK} width={34} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(1)} />
              <Tooltip contentStyle={TOOLTIP} labelFormatter={(d) => String(d)} formatter={(v) => [Number(v).toFixed(3), "NDVI"]} />
              <Line dataKey="value" stroke={shown.colour} strokeWidth={1.6} dot={false} isAnimationActive={false} />
              {data.seasons.flatMap((s) => [
                <ReferenceDot key={`s${s.year}`} x={nearest(data.smoothed, s.start)} y={value(s.start)} r={3} fill="var(--accent)" stroke="none" />,
                <ReferenceDot key={`p${s.year}`} x={nearest(data.smoothed, s.peak)} y={value(s.peak)} r={3.5} fill="var(--ink)" stroke="none" />,
                <ReferenceDot key={`e${s.year}`} x={nearest(data.smoothed, s.end)} y={value(s.end)} r={3} fill="var(--warning)" stroke="none" />,
              ])}
            </LineChart>
          </ResponsiveContainer>
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
            {data.summary.map((line) => (
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
function nearest(points: { date: string }[], date: string): string {
  const t = +new Date(date);
  return points.reduce((a, b) => (Math.abs(+new Date(b.date) - t) < Math.abs(+new Date(a.date) - t) ? b : a)).date;
}
