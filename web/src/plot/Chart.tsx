import * as Plot from "@observablehq/plot";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ContextMenu, { type MenuItem } from "../components/ContextMenu";
import { num } from "../format";
import { draw } from "./draw";
import { exportPng, exportSvg } from "./figure";
import { dateOf, monthOf, useHover, useTime, type Span } from "./time";

// Every chart in Magonia is drawn by Observable Plot through this frame: it fits the chart
// to its width, redraws it when the width changes, and offers the figure as a file.

type Options = Plot.PlotOptions;

function useWidth() {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    if (!box.current) return;
    const seen = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    seen.observe(box.current);
    return () => seen.disconnect();
  }, []);
  return [box, width] as const;
}

type FrameProps = {
  title: string; // names the figure file and the chart for screen readers
  options: Options; // everything but the width
  height: number;
  menu?: MenuItem[]; // extra items before the export ones
  overlay?: (plot: SVGSVGElement) => ReactNode;
  onPointer?: {
    move?: (x: number, plot: SVGSVGElement) => void;
    leave?: () => void;
    down?: (x: number, plot: SVGSVGElement) => void;
    up?: (x: number, plot: SVGSVGElement) => void;
    double?: () => void;
  };
  source?: string;
};

export function PlotFrame({ title, options, height, menu = [], overlay, onPointer, source }: FrameProps) {
  const [box, width] = useWidth();
  const holder = useRef<HTMLDivElement>(null);
  const [plot, setPlot] = useState<SVGSVGElement | null>(null);
  const [opened, setOpened] = useState<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (!width || !holder.current) return;
    const svg = draw({ ...options, height }, width);
    svg.classList.add("plot-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", title);
    holder.current.replaceChildren(svg);
    setPlot(svg);
  }, [options, height, width, title]);

  const redraw = useCallback((px: number) => draw({ ...options, height: Math.round(height * 0.8) }, px, true), [options, height]);
  const items: MenuItem[] = [
    ...menu,
    ...(menu.length ? (["divider"] as MenuItem[]) : []),
    { label: "Export SVG · single column (85 mm)", run: () => exportSvg(redraw, title, "single") },
    { label: "Export SVG · double column (175 mm)", run: () => exportSvg(redraw, title, "double") },
    { label: "Export PNG · 300 dpi, single column", run: () => void exportPng(redraw, title, "single") },
    { label: "Export PNG · 300 dpi, double column", run: () => void exportPng(redraw, title, "double") },
  ];
  const x = (e: React.PointerEvent | React.MouseEvent) => e.clientX - (plot?.getBoundingClientRect().left ?? 0);

  return (
    <figure className="chart" style={{ minHeight: height }}>
      <div
        ref={box}
        className="chart-box"
        onPointerMove={(e) => plot && onPointer?.move?.(x(e), plot)}
        onPointerLeave={() => onPointer?.leave?.()}
        onPointerDown={(e) => e.button === 0 && plot && onPointer?.down?.(x(e), plot)}
        onPointerUp={(e) => e.button === 0 && plot && onPointer?.up?.(x(e), plot)}
        onDoubleClick={() => onPointer?.double?.()}
        onContextMenu={(e) => {
          e.preventDefault();
          setOpened({ x: e.clientX, y: e.clientY });
        }}
      >
        <div ref={holder} />
        {plot && overlay?.(plot)}
      </div>
      {source && <figcaption className="chart-source">{source}</figcaption>}
      {opened && <ContextMenu x={opened.x} y={opened.y} items={items} onClose={() => setOpened(null)} />}
    </figure>
  );
}

// Time series: lines with a shaded band, hollow points for filled values, years on the axis.
// Hover marks the date on every chart, a click picks the month for the map, a drag zooms
// every chart to the same years, and a double click zooms out.

export type TimePoint = { date: Date; value: number | null; low?: number | null; high?: number | null; filled?: boolean };
export type TimeSeries = { id: string; name: string; colour: string; points: TimePoint[]; dashed?: boolean; width?: number; opacity?: number; dots?: boolean };

type TimeProps = {
  title: string;
  series: TimeSeries[];
  height?: number;
  y: { label: string; digits: number; domain?: [number, number]; zero?: boolean; ticks?: number[] };
  source?: string;
  marks?: Plot.Markish[]; // drawn over the lines
  linked?: boolean; // false for charts whose dates are not calendar dates the map can show
};

export function TimeChart({ title, series, height = 200, y, source, marks = [], linked = true }: TimeProps) {
  const { zoom, setZoom, setMonth, month } = useTime();
  const [drag, setDrag] = useState<{ from: number; to: number } | null>(null);
  const [pointed, setPointed] = useState(false); // the values are listed only on the chart under the pointer
  const { setHover } = useHover();

  const dates = useMemo(() => {
    const all = new Map<number, Date>();
    for (const s of series) for (const p of s.points) all.set(+p.date, p.date);
    return [...all.values()].sort((a, b) => +a - +b);
  }, [series]);

  const options = useMemo<Options>(() => {
    const rows = series.flatMap((s) => s.points.map((p) => ({ ...p, id: s.id })));
    const colour = Object.fromEntries(series.map((s) => [s.id, s.colour]));
    const extent = dates.length ? ([dates[0], dates[dates.length - 1]] as Span) : undefined;
    return {
      x: { type: "utc", domain: zoom ?? extent, label: null, ticks: 8, tickSize: 4 },
      y: {
        label: y.label,
        labelArrow: "none",
        domain: y.domain,
        ticks: y.ticks ?? 5,
        grid: true,
        nice: !y.domain,
        tickFormat: (v: number) => num(v, y.digits),
        tickSize: 0,
      },
      marks: [
        ...(y.zero ? [Plot.ruleY([0], { stroke: "currentColor", strokeOpacity: 0.45 })] : []),
        Plot.areaY(rows.filter((r) => r.low != null && r.high != null), {
          x: "date",
          y1: "low",
          y2: "high",
          z: "id",
          fill: (r: { id: string }) => colour[r.id],
          fillOpacity: 0.13,
          clip: true,
        }),
        ...series.map((s) =>
          Plot.lineY(s.points, {
            x: "date",
            y: (p: TimePoint) => p.value ?? NaN, // a missing value breaks the line
            stroke: s.colour,
            strokeWidth: s.width ?? 1.5,
            strokeOpacity: s.opacity ?? 1,
            strokeDasharray: s.dashed ? "4 3" : undefined,
            clip: true,
          }),
        ),
        ...series
          .filter((s) => s.dots)
          .map((s) => Plot.dot(s.points.filter((p) => p.value !== null), { x: "date", y: "value", r: 2.2, fill: s.colour, clip: true })),
        ...series.map((s) =>
          Plot.dot(s.points.filter((p) => p.filled), { x: "date", y: "value", r: 2.5, stroke: s.colour, fill: "var(--card, white)", strokeWidth: 1.2, clip: true }),
        ),
        ...marks,
      ],
    };
  }, [series, dates, zoom, y, marks]);

  const nearest = useCallback(
    (x: number, plot: SVGSVGElement) => {
      if (!dates.length) return null;
      const scale = (plot as unknown as { scale: (n: string) => { invert: (x: number) => Date } }).scale?.("x");
      if (!scale) return null;
      const at = +scale.invert(x);
      let best = dates[0];
      for (const d of dates) if (Math.abs(+d - at) < Math.abs(+best - at)) best = d;
      return best;
    },
    [dates],
  );

  const toDate = (x: number, plot: SVGSVGElement) => (plot as unknown as { scale: (n: string) => { invert: (x: number) => Date } }).scale("x").invert(x);

  const menu: MenuItem[] = [
    ...(zoom ? [{ label: "Zoom out to every year", run: () => setZoom(null), hint: "Double-click" }] : []),
    {
      label: "Copy values as CSV",
      run: () => {
        const lines = ["series,date,value"];
        for (const s of series) for (const p of s.points) lines.push(`${JSON.stringify(s.name)},${p.date.toISOString().slice(0, 10)},${p.value ?? ""}`);
        void navigator.clipboard?.writeText(lines.join("\n"));
      },
    },
  ];

  return (
    <PlotFrame
      title={title}
      options={options}
      height={height}
      source={source}
      menu={menu}
      onPointer={{
        move: (x, plot) => {
          if (!pointed) setPointed(true);
          if (drag) setDrag({ ...drag, to: x });
          if (linked) setHover(nearest(x, plot));
        },
        leave: () => {
          setPointed(false);
          setHover(null);
          setDrag(null);
        },
        down: (x) => setDrag({ from: x, to: x }),
        up: (x, plot) => {
          if (drag && Math.abs(drag.to - drag.from) > 6) {
            const a = toDate(Math.min(drag.from, x), plot);
            const b = toDate(Math.max(drag.from, x), plot);
            setZoom([a, b]);
          } else if (linked) {
            const d = nearest(x, plot);
            if (d) setMonth(monthOf(d) === month ? null : monthOf(d));
          }
          setDrag(null);
        },
        double: () => setZoom(null),
      }}
      overlay={(plot) => <TimeOverlay plot={plot} series={series} digits={y.digits} drag={drag} linked={linked} tip={pointed} />}
    />
  );
}

type Scale = { apply: (d: Date) => number; range: [number, number] };

function TimeOverlay({ plot, series, digits, drag, linked, tip }: { plot: SVGSVGElement; series: TimeSeries[]; digits: number; drag: { from: number; to: number } | null; linked: boolean; tip: boolean }) {
  const { hover } = useHover();
  const { month } = useTime();
  const x = (plot as unknown as { scale: (n: string) => Scale }).scale?.("x");
  const yScale = (plot as unknown as { scale: (n: string) => { range: [number, number] } }).scale?.("y");
  if (!x || !yScale) return null;
  const [top, bottom] = [Math.min(...yScale.range), Math.max(...yScale.range)];
  const left = x.apply;
  const inside = (px: number) => px >= Math.min(...x.range) - 1 && px <= Math.max(...x.range) + 1;
  // the chosen month is marked at its first date in the series, else at its first day
  const chosen = linked && month ? (series.flatMap((s) => s.points).find((p) => monthOf(p.date) === month)?.date ?? dateOf(`${month}-01`)) : null;
  const rows = hover
    ? series.map((s) => ({ s, p: s.points.find((p) => +p.date === +hover) })).filter((r) => r.p && r.p.value !== null)
    : [];
  const hx = hover ? left(hover) : NaN;

  return (
    <div className="chart-overlay" aria-hidden="true">
      {chosen && inside(left(chosen)) && <div className="chart-rule chosen" style={{ left: left(chosen), top, height: bottom - top }} />}
      {hover && inside(hx) && <div className="chart-rule" style={{ left: hx, top, height: bottom - top }} />}
      {drag && Math.abs(drag.to - drag.from) > 2 && (
        <div className="chart-brush" style={{ left: Math.min(drag.from, drag.to), width: Math.abs(drag.to - drag.from), top, height: bottom - top }} />
      )}
      {tip && hover && inside(hx) && rows.length > 0 && (
        <div className={`chart-tip${hx > plot.clientWidth / 2 ? " left" : ""}`} style={{ left: hx, top }}>
          <div className="chart-tip-date">{hover.toISOString().slice(0, 10)}</div>
          {rows.map(({ s, p }) => (
            <div key={s.id} className="chart-tip-row">
              <span className="swatch" style={{ background: s.colour }} />
              <span className="chart-tip-name">{s.name}</span>
              <span className="chart-tip-value">
                {num(p!.value, digits + 1)}
                {p!.low != null && p!.high != null && <span className="meta"> ±{num((p!.high - p!.low) / 2, digits + 1)}</span>}
                {p!.filled && <span className="meta"> filled</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
