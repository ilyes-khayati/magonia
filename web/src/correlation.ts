import type { SeriesPoint } from "./api";
import { observed } from "./stats";

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

// Month index from "YYYY-MM-DD", so that consecutive months differ by one
const monthIndex = (date: string) => Number(date.slice(0, 4)) * 12 + Number(date.slice(5, 7)) - 1;

// Real observations (not filled) averaged by calendar month, since the products have different dates
export function monthly(points: SeriesPoint[]): Map<number, number> {
  const byMonth = new Map<number, number[]>();
  for (const p of observed(points)) {
    if (p.filled) continue;
    const m = monthIndex(p.date);
    byMonth.set(m, [...(byMonth.get(m) ?? []), p.value]);
  }
  return new Map([...byMonth].map(([m, values]) => [m, mean(values)]));
}

// Each value minus the average of its calendar month: what is left is the
// year-to-year variation, without the shared seasonal cycle
export function anomalies(series: Map<number, number>): Map<number, number> {
  const byCalendar: number[][] = Array.from({ length: 12 }, () => []);
  for (const [m, v] of series) byCalendar[m % 12].push(v);
  const climatology = byCalendar.map((values) => (values.length ? mean(values) : NaN));
  return new Map([...series].map(([m, v]) => [m, v - climatology[m % 12]]));
}

export function pearson(xs: number[], ys: number[]): number {
  const mx = mean(xs);
  const my = mean(ys);
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < xs.length; i++) {
    sxy += (xs[i] - mx) * (ys[i] - my);
    sxx += (xs[i] - mx) ** 2;
    syy += (ys[i] - my) ** 2;
  }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : NaN;
}

export type Lag = { lag: number; r: number; n: number; band: number };

export const MIN_PAIRS = 12;

// Correlation between the response and the driver *lag* months earlier, for each lag.
// The band is the approximate 95% limit for no correlation (±1.96/√n); it ignores
// autocorrelation, so it is optimistic for smooth series.
export function lagCorrelation(
  response: SeriesPoint[],
  driver: SeriesPoint[],
  maxLag = 12,
  deseasonalise = true,
): Lag[] {
  let a = monthly(response);
  let b = monthly(driver);
  if (deseasonalise) {
    a = anomalies(a);
    b = anomalies(b);
  }
  const lags: Lag[] = [];
  for (let lag = 0; lag <= maxLag; lag++) {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const [m, value] of a) {
      const earlier = b.get(m - lag);
      if (earlier === undefined) continue;
      xs.push(earlier);
      ys.push(value);
    }
    const r = xs.length >= MIN_PAIRS ? pearson(xs, ys) : NaN;
    if (!Number.isNaN(r)) lags.push({ lag, r, n: xs.length, band: 1.96 / Math.sqrt(xs.length) });
  }
  return lags;
}

// The lag with the strongest correlation, positive or negative
export const strongest = (lags: Lag[]) =>
  lags.length ? lags.reduce((a, b) => (Math.abs(b.r) > Math.abs(a.r) ? b : a)) : null;

// One plain sentence for an area, computed from the numbers
export function describeLink(area: string, response: string, driver: string, lags: Lag[], deseasonalise: boolean) {
  const best = strongest(lags);
  if (!best) return `${area}: no correlation can be computed (fewer than ${MIN_PAIRS} months in common, or no variation left).`;
  const what = deseasonalise ? "anomalies" : "values";
  const when = best.lag === 0 ? "from the same month" : `from ${best.lag} month${best.lag > 1 ? "s" : ""} earlier`;
  const r = `r = ${best.r.toFixed(2)}`;
  if (Math.abs(best.r) < best.band) {
    return `${area}: no lag stands out from chance (strongest ${r}, with ${driver} ${when}).`;
  }
  const direction = best.r > 0 ? "higher" : "lower";
  const weak = Math.abs(best.r) < 0.3 ? ", weak" : "";
  return `${area}: ${response} ${what} are most closely linked to ${driver} ${what} ${when} (${r}${weak}): higher ${driver} goes with ${direction} ${response}.`;
}

// Share of a monthly series' variance explained by its calendar-month means (as the engine's
// guardrails compute it)
export function seasonalShare(series: Map<number, number>): number {
  const values = [...series.values()];
  if (values.length < 24) return 0;
  const spread = (xs: number[]) => {
    const m = mean(xs);
    return xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1);
  };
  const total = spread(values);
  return total ? 1 - spread([...anomalies(series).values()]) / total : 0;
}

export const SEASONAL = 0.5;
export const MIN_MONTHS = 36;

// The guardrails on a correlation (AI-03), worded as the engine words them for Magonia
export function correlationCautions(
  area: string,
  response: string,
  driver: string,
  a: SeriesPoint[],
  b: SeriesPoint[],
  deseasonalise: boolean,
): string[] {
  const ma = monthly(a);
  const mb = monthly(b);
  const out: string[] = [];
  const sa = seasonalShare(ma);
  const sb = seasonalShare(mb);
  if (!deseasonalise && Math.min(sa, sb) > SEASONAL)
    out.push(
      `${area}: ${response} and ${driver} both follow a yearly cycle (${Math.round(100 * sa)}% and ${Math.round(100 * sb)}% of their variance), and it was not removed, so most of the correlation is the shared season. Tick 'Remove seasonal cycle' to see the link beyond it.`,
    );
  const months = [...ma.keys()].filter((m) => mb.has(m)).length;
  if (months < MIN_MONTHS)
    out.push(`${area}: only ${months} months in common; a correlation needs about ${MIN_MONTHS} to mean much.`);
  return out;
}
