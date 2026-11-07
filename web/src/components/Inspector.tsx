import { useEffect, useMemo, useState } from "react";
import { inspectPoint, type PointSeries, type Variable, type VariableKey } from "../api";
import { coordinate, num } from "../format";
import { square } from "../geo";
import { TimeChart } from "../plot/Chart";
import { dateOf, useTime } from "../plot/time";
import { large } from "../variables";
import { yLabel } from "../plot/series";
import { CloseIcon } from "./Icons";

type Props = {
  at: [number, number];
  catalogue: Variable[];
  variable: VariableKey;
  start: string; // "YYYY-MM"
  end: string; // last month, included
  scale?: number;
  onVariable: (key: VariableKey) => void;
  onMakeArea: (geometry: GeoJSON.Polygon, name: string) => void;
  onClose: () => void;
};

const nextMonth = (month: string) => {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 10);
};

// One pixel, not an area: its value over time, read straight from Earth Engine
export default function Inspector({ at, catalogue, variable, start, end, scale, onVariable, onMakeArea, onClose }: Props) {
  const [found, setFound] = useState<PointSeries | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { month } = useTime();
  const meta = catalogue.find((v) => v.key === variable);
  const digits = large(variable) ? 1 : 2;

  useEffect(() => {
    let current = true;
    inspectPoint({ variable, lon: at[0], lat: at[1], start: `${start}-01`, end: nextMonth(end), scale: variable === "spei" ? (scale ?? 3) : undefined })
      .then((r) => current && setFound(r))
      .catch((e) => current && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      current = false;
    };
  }, [at, variable, start, end, scale]);

  const series = useMemo(
    () => (found ? [{ id: "pixel", name: "This pixel", colour: "var(--accent)", width: 1.3, points: found.points.map((p) => ({ date: dateOf(p.date), value: p.value })) }] : []),
    [found],
  );
  const inMonth = found && month ? found.points.filter((p) => p.date.startsWith(month) && p.value !== null) : [];
  const monthValue = inMonth.length ? inMonth.reduce((a, p) => a + p.value!, 0) / inMonth.length : null;
  const valid = found?.points.filter((p) => p.value !== null).length ?? 0;

  return (
    <section className="floating panel inspector" aria-label="Pixel inspector">
      <header className="panel-head">
        <h3>Inspector</h3>
        <button className="icon-button" aria-label="Close the inspector" title="Close (Esc)" onClick={onClose}>
          <CloseIcon size={14} />
        </button>
      </header>
      <dl className="facts">
        <dt>Point</dt>
        <dd className="mono">{coordinate(at[0], at[1])}</dd>
        <dt>Variable</dt>
        <dd>
          <select className="select" value={variable} onChange={(e) => onVariable(e.target.value as VariableKey)}>
            {catalogue.map((v) => (
              <option key={v.key} value={v.key}>
                {v.name}
              </option>
            ))}
          </select>
        </dd>
        {found && (
          <>
            <dt>Pixel</dt>
            <dd>
              {found.pixel_m >= 1000 ? `${found.pixel_m / 1000} km` : `${found.pixel_m} m`} · {valid} of {found.points.length} dates with a value
            </dd>
            {month && (
              <>
                <dt>{month}</dt>
                <dd className="mono">
                  {monthValue === null ? "no value" : num(monthValue, digits + 1)}
                  {meta?.units && monthValue !== null ? ` ${meta.units}` : ""}
                </dd>
              </>
            )}
          </>
        )}
      </dl>
      {error ? (
        <p className="error-text">{error}</p>
      ) : !found ? (
        <p className="meta" role="status">
          Reading {meta?.name} at this pixel from {start} to {end}…
        </p>
      ) : (
        <TimeChart title={`${meta?.name ?? variable} at ${coordinate(at[0], at[1], 4)}`} series={series} height={150} y={{ label: meta ? yLabel(meta) : variable, digits: digits - 1 }} />
      )}
      {found && (
        <button className="text-button" onClick={() => onMakeArea(square(at, found.pixel_m), `Pixel ${at[1].toFixed(4)}, ${at[0].toFixed(4)}`)}>
          Make this pixel an area
        </button>
      )}
    </section>
  );
}
