import type { SeriesPoint } from "./api";

// How the Data page shows a series, computed in the browser from what was extracted, so that
// changing it never asks Earth Engine again. Analyses keep the series as extracted.
export type Display = {
  smooth: boolean; // Savitzky–Golay, 5 points, quadratic (PREP-04)
  anomaly: { from: number; to: number } | null; // minus each calendar month's mean over these years (PREP-06)
  months: number[]; // calendar months shown, 1 to 12; empty for all (TIME-04)
};

export const NO_DISPLAY: Display = { smooth: false, anomaly: null, months: [] };

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const month = (date: string) => Number(date.slice(5, 7));
const year = (date: string) => Number(date.slice(0, 4));
const real = (p: SeriesPoint) => p.value !== null && !p.masked;

// Savitzky–Golay weights for 5 points and a quadratic (Savitzky and Golay 1964)
const SG5 = [-3, 12, 17, 12, -3].map((w) => w / 35);

export function smoothed(points: SeriesPoint[]): SeriesPoint[] {
  const shown = points.map((p, i) => ({ p, i })).filter(({ p }) => real(p) || p.filled);
  const out = points.map((p) => ({ ...p }));
  for (let k = 2; k < shown.length - 2; k++) {
    const window = shown.slice(k - 2, k + 3).map(({ p }) => p.value!);
    out[shown[k].i].value = window.reduce((a, v, j) => a + v * SG5[j], 0);
  }
  return out;
}

// Each value minus the mean of its calendar month over the reference years
export function anomalies(points: SeriesPoint[], from: number, to: number): SeriesPoint[] {
  const sums = new Map<number, [number, number]>();
  for (const p of points) {
    if (!real(p) || p.filled || year(p.date) < from || year(p.date) > to) continue;
    const [s, n] = sums.get(month(p.date)) ?? [0, 0];
    sums.set(month(p.date), [s + p.value!, n + 1]);
  }
  return points.map((p) => {
    const ref = sums.get(month(p.date));
    return p.value === null || !ref ? { ...p, value: null } : { ...p, value: p.value - ref[0] / ref[1] };
  });
}

export function display(points: SeriesPoint[], d: Display): SeriesPoint[] {
  let out = points;
  if (d.anomaly) out = anomalies(out, d.anomaly.from, d.anomaly.to);
  if (d.smooth) out = smoothed(out);
  if (d.months.length) out = out.filter((p) => d.months.includes(month(p.date)));
  return out;
}

// What the charts show, in words, for their subtitle and for Magonia
export function describeDisplay(d: Display): string | null {
  const parts = [];
  if (d.anomaly) parts.push(`anomalies against the ${d.anomaly.from}–${d.anomaly.to} mean of each month`);
  if (d.smooth) parts.push("smoothed (Savitzky–Golay, 5 points)");
  if (d.months.length && d.months.length < 12) parts.push(`only ${d.months.map((m) => MONTHS[m - 1]).join(", ")}`);
  return parts.length ? parts.join(", ") : null;
}
