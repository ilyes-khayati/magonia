import * as Plot from "@observablehq/plot";

type Options = Plot.PlotOptions;

const BASE: Options = {
  style: { fontFamily: "inherit", fontSize: "11px", fontVariantNumeric: "tabular-nums", overflow: "visible" },
  marginTop: 26,
  marginRight: 12,
  marginBottom: 26,
  marginLeft: 44,
};

// Charts are drawn as figures: a frame around the plot, tick marks pointing out, a few round
// ticks rather than many, and axis titles with their units
export function draw(options: Options, width: number, forFile = false): SVGSVGElement {
  const style = forFile ? { ...(BASE.style as object), fontSize: "8pt" } : BASE.style;
  const height = options.height ?? 200;
  // dates need room: about one label per 70 pixels
  const x = options.x?.type === "utc" && typeof options.x.ticks === "number" ? { ...options.x, ticks: Math.min(options.x.ticks, Math.max(2, Math.floor(width / 70))) } : options.x;
  // about one value label per 45 pixels of height
  const y = options.y && options.y.axis !== null ? { ...options.y, ticks: options.y.ticks ?? Math.max(3, Math.floor(height / 45)), tickSize: 4 } : options.y;
  const framed = [Plot.frame({ stroke: "currentColor", strokeOpacity: 0.55 })];
  const svg = Plot.plot({ ...BASE, ...options, x: x && x.axis !== null ? { ...x, tickSize: 4 } : x, y, style, width, marks: [...(options.marks ?? []), ...framed] }) as unknown as SVGSVGElement;
  // the chart is one image to a screen reader; its parts keep their names for tests and styles
  for (const g of svg.querySelectorAll("[aria-label]")) {
    g.setAttribute("data-mark", g.getAttribute("aria-label")!);
    g.removeAttribute("aria-label");
  }
  return svg;
}

