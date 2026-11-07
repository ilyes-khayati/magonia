import * as Plot from "@observablehq/plot";

type Options = Plot.PlotOptions;

const BASE: Options = {
  style: { fontFamily: "inherit", fontSize: "11px", fontVariantNumeric: "tabular-nums", overflow: "visible" },
  marginTop: 26,
  marginRight: 12,
  marginBottom: 26,
  marginLeft: 44,
};

export function draw(options: Options, width: number, forFile = false): SVGSVGElement {
  const style = forFile ? { ...(BASE.style as object), fontSize: "8pt" } : BASE.style;
  // dates need room: about one label per 70 pixels
  const x = options.x?.type === "utc" && typeof options.x.ticks === "number" ? { ...options.x, ticks: Math.min(options.x.ticks, Math.max(2, Math.floor(width / 70))) } : options.x;
  const svg = Plot.plot({ ...BASE, ...options, x, style, width }) as unknown as SVGSVGElement;
  // the chart is one image to a screen reader; its parts keep their names for tests and styles
  for (const g of svg.querySelectorAll("[aria-label]")) {
    g.setAttribute("data-mark", g.getAttribute("aria-label")!);
    g.removeAttribute("aria-label");
  }
  return svg;
}

