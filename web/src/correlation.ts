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

// band: the single-lag 95% limit (±1.96/√n), drawn on the chart. memory: the lag-1
// autocorrelation of the two series, for the test of the strongest of several lags
export type Lag = { lag: number; r: number; n: number; band: number; memory?: [number, number] };

// Lag-1 autocorrelation of a monthly series, each month paired with the month before
function memoryOf(series: Map<number, number>): number {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const [m, v] of series) {
    const before = series.get(m - 1);
    if (before === undefined) continue;
    xs.push(before);
    ys.push(v);
  }
  const r = xs.length > 2 ? pearson(xs, ys) : 0;
  return Number.isNaN(r) ? 0 : r;
}

// Inverse of the standard normal distribution (Acklam's rational approximation, |error| < 1.2e-9)
export function normalQuantile(p: number): number {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155211224];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const low = 0.02425;
  if (p < low) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > 1 - low) return -normalQuantile(1 - p);
  const q = p - 0.5;
  const r = q * q;
  return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

// The |r| the strongest of `tests` lags (or scale and lag cells) must pass to stand out from
// chance: 5%, two-sided, Bonferroni over what was searched, on the effective number of months
// of two autocorrelated series (Bretherton et al. 1999). The same test as the engine's, so
// the card and Magon give the same verdict (review of 18 Nov)
export function searchedBand(best: Lag, tests: number): number {
  const [ra, rb] = best.memory ?? [0, 0];
  const effective = (best.n * (1 - ra * rb)) / (1 + ra * rb);
  return normalQuantile(1 - 0.05 / (2 * tests)) / Math.sqrt(Math.max(effective, 4));
}

export const MIN_PAIRS = 12;

// Correlation between the response and the driver *lag* months earlier, for each lag.
// The band is the approximate 95% limit for one lag (±1.96/√n), for the chart; the verdict on
// the strongest lag uses searchedBand.
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
  const memory: [number, number] = [memoryOf(a), memoryOf(b)];
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
    if (!Number.isNaN(r)) lags.push({ lag, r, n: xs.length, band: 1.96 / Math.sqrt(xs.length), memory });
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
  const bound = searchedBand(best, lags.length);
  const r = `r = ${best.r.toFixed(2)}`;
  if (Math.abs(best.r) < bound) {
    return `${area}: no lag stands out from chance (strongest ${r}, with ${driver} ${when}; the strongest of ${lags.length} lags must pass ±${bound.toFixed(2)}).`;
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
