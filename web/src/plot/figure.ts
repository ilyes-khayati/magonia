// Charts as figure files for a paper: vector SVG, or PNG at 300 dpi, at a journal's column
// width. The page's colours are CSS variables, which a file cannot read, so the colours each
// element is drawn with are written into it.

export const WIDTHS = { single: 85, double: 175 } as const; // millimetres
export type Width = keyof typeof WIDTHS;

const PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-opacity", "opacity", "fill-opacity", "font-size", "font-family", "font-weight", "font-variant-numeric"];

// A copy of an SVG with its computed styles written in, so it stands alone
export function standalone(svg: SVGSVGElement, { ink = "#111111", font = "Inter, Helvetica, Arial, sans-serif" } = {}): SVGSVGElement {
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const from = [svg, ...svg.querySelectorAll("*")];
  const to = [copy, ...copy.querySelectorAll("*")];
  from.forEach((el, i) => {
    const style = getComputedStyle(el);
    for (const p of PROPS) {
      let value = style.getPropertyValue(p);
      if (p === "font-family") value = font;
      (to[i] as SVGElement).style.setProperty(p, value);
    }
  });
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.style.color = ink;
  copy.style.background = "white";
  return copy;
}

function save(blob: Blob, name: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

export const fileName = (title: string) => title.replace(/\W+/g, "-").replace(/^-|-$/g, "").toLowerCase() || "figure";

// The chart drawn again by `draw` at the column width, then saved
export function exportSvg(draw: (widthPx: number) => SVGSVGElement, title: string, width: Width) {
  const mm = WIDTHS[width];
  const px = Math.round((mm / 25.4) * 96);
  const svg = mount(draw(px));
  const copy = standalone(svg);
  svg.parentElement?.remove();
  const h = Number(copy.getAttribute("height")) || copy.clientHeight;
  copy.setAttribute("viewBox", `0 0 ${px} ${h}`);
  copy.setAttribute("width", `${mm}mm`);
  copy.setAttribute("height", `${((h / px) * mm).toFixed(1)}mm`);
  save(new Blob([new XMLSerializer().serializeToString(copy)], { type: "image/svg+xml" }), `${fileName(title)}-${mm}mm.svg`);
}

export async function exportPng(draw: (widthPx: number) => SVGSVGElement, title: string, width: Width, dpi = 300) {
  const mm = WIDTHS[width];
  const px = Math.round((mm / 25.4) * 96);
  const svg = mount(draw(px));
  const copy = standalone(svg);
  svg.parentElement?.remove();
  const h = Number(copy.getAttribute("height")) || 200;
  copy.setAttribute("width", String(px));
  copy.setAttribute("height", String(h));
  const image = await load(new XMLSerializer().serializeToString(copy));
  const scale = dpi / 96;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(px * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "white";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (blob) save(blob, `${fileName(title)}-${mm}mm-${dpi}dpi.png`);
}

// Computed styles need the element in the page; it is placed out of sight for a moment
function mount(svg: SVGSVGElement): SVGSVGElement {
  const holder = document.createElement("div");
  holder.style.cssText = "position:fixed;left:-10000px;top:0;color:#111;font-size:8pt";
  holder.className = "figure-export";
  holder.append(svg);
  document.body.append(holder);
  return svg;
}

export function load(svg: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
}
