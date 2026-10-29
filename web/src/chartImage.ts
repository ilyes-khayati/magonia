// A card's charts as one PNG (VIS-06): each chart's SVG with its colours written in (they are
// CSS variables on the page, which an image file cannot read), stacked under the card's title
// at twice the screen's resolution.

const PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "opacity", "fill-opacity", "font-size", "font-family", "font-weight"];

function inline(svg: SVGSVGElement): string {
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const from = [svg, ...svg.querySelectorAll("*")];
  const to = [copy, ...copy.querySelectorAll("*")];
  from.forEach((el, i) => {
    const style = getComputedStyle(el);
    for (const p of PROPS) (to[i] as SVGElement).style.setProperty(p, style.getPropertyValue(p));
  });
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.setAttribute("width", String(svg.clientWidth));
  copy.setAttribute("height", String(svg.clientHeight));
  return new XMLSerializer().serializeToString(copy);
}

function load(svg: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
}

export async function chartImage(
  card: HTMLElement,
  title: string,
  subtitle = "",
  { scale = 2, type = "image/png", quality }: { scale?: number; type?: string; quality?: number } = {},
): Promise<Blob | null> {
  const svgs = [...card.querySelectorAll<SVGSVGElement>("svg.recharts-surface")];
  if (!svgs.length) return null;
  const page = getComputedStyle(document.documentElement);
  const ink = page.getPropertyValue("--ink").trim() || "#17201b";
  const muted = page.getPropertyValue("--muted").trim() || "#56605a";
  const background = page.getPropertyValue("--card").trim() || "#ffffff";
  const images = await Promise.all(svgs.map((s) => load(inline(s))));
  const pad = 16;
  const head = subtitle ? 48 : 32;
  const width = Math.max(...svgs.map((s) => s.clientWidth)) + 2 * pad;
  const height = head + svgs.reduce((h, s) => h + s.clientHeight + 8, 0) + pad;
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(scale, scale);
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = ink;
  ctx.font = "600 14px 'IBM Plex Sans', system-ui, sans-serif";
  ctx.fillText(title, pad, pad + 10);
  if (subtitle) {
    ctx.fillStyle = muted;
    ctx.font = "11px 'IBM Plex Sans', system-ui, sans-serif";
    ctx.fillText(subtitle, pad, pad + 28);
  }
  let y = head;
  images.forEach((img, i) => {
    ctx.drawImage(img, pad, y, svgs[i].clientWidth, svgs[i].clientHeight);
    y += svgs[i].clientHeight + 8;
  });
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

export async function saveChartImage(card: HTMLElement, title: string, subtitle = "") {
  const blob = await chartImage(card, title, subtitle);
  if (!blob) return;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${title.replace(/\W+/g, "-").toLowerCase()}.png`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// A small picture of a card for the board: JPEG at screen resolution, as a data URL
export async function chartSnapshot(card: HTMLElement, title: string): Promise<string | undefined> {
  const blob = await chartImage(card, title, "", { scale: 1, type: "image/jpeg", quality: 0.82 });
  if (!blob) return undefined;
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsDataURL(blob);
  });
}
