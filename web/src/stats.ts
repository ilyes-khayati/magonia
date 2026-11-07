import type { SeriesPoint } from "./api";
import { large } from "./variables";

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

// Real observations only: filled values are excluded from every statistic
export const observed = (points: SeriesPoint[]) =>
  points.filter((p) => p.value !== null && !p.masked) as (SeriesPoint & { value: number })[];

export type Stats = { mean: number; min: number; max: number; sd: number; n: number; filled: number };

export function describe(points: SeriesPoint[]): Stats | null {
  const values = observed(points).map((p) => p.value);
  if (!values.length) return null;
  const m = mean(values);
  return {
    mean: m,
    min: Math.min(...values),
    max: Math.max(...values),
    sd: Math.sqrt(mean(values.map((v) => (v - m) ** 2))),
    n: values.length,
    filled: points.filter((p) => p.filled).length,
  };
}

export type MonthStats = { month: number; mean: number; median: number; low: number; high: number; years: number };

export function median(xs: number[]): number {
  const sorted = [...xs].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// The value below which a share q of the values fall, interpolated between neighbours
export function quantile(xs: number[], q: number): number {
  const sorted = [...xs].sort((a, b) => a - b);
  const at = (sorted.length - 1) * q;
  const low = Math.floor(at);
  return sorted[low] + (sorted[Math.min(low + 1, sorted.length - 1)] - sorted[low]) * (at - low);
}

// Meteorological seasons, as the season boxplots group months
export const SEASONS = ["Winter", "Spring", "Summer", "Autumn"] as const;
export const seasonOf = (month: number) => SEASONS[Math.floor(((month + 1) % 12) / 3)]; // Dec–Feb is winter

// One row per real observation, labelled by calendar month and season, for distributions
export function observations(points: SeriesPoint[]) {
  return observed(points).map((p) => {
    const month = Number(p.date.slice(5, 7)) - 1;
    return { value: p.value, month, season: seasonOf(month), year: Number(p.date.slice(0, 4)) };
  });
}

// Values by calendar month across years: the average year, with the lowest and highest year
export function seasonalCycle(points: SeriesPoint[]): MonthStats[] {
  const byMonth: number[][] = MONTHS.map(() => []);
  for (const point of observed(points)) byMonth[Number(point.date.slice(5, 7)) - 1].push(point.value);
  return byMonth.flatMap((values, month) =>
    values.length
      ? [{ month, mean: mean(values), median: median(values), low: Math.min(...values), high: Math.max(...values), years: values.length }]
      : [],
  );
}

export type Named = { name: string; units: string; key: string; points: SeriesPoint[] };

const fmt = (value: number, key: string) => value.toFixed(large(key) ? 1 : 2);
const unit = (s: Named) => (s.units ? ` ${s.units}` : "");

// Plain sentences computed from the numbers, for the summary card
export function summarise(variable: string, series: Named[]): string[] {
  const lines: string[] = [];
  const cycles = series.map((s) => ({ s, cycle: seasonalCycle(s.points) })).filter((c) => c.cycle.length);

  for (const { s, cycle } of cycles) {
    const peak = cycle.reduce((a, b) => (b.mean > a.mean ? b : a));
    const low = cycle.reduce((a, b) => (b.mean < a.mean ? b : a));
    if (s.key === "spei") {
      const values = observed(s.points);
      const driest = values.reduce((a, b) => (b.value < a.value ? b : a));
      const severity = driest.value <= -2 ? "extreme drought" : driest.value <= -1.5 ? "severe drought" : driest.value <= -1 ? "moderate drought" : "no drought";
      lines.push(`${s.name}: ${variable} is lowest in ${driest.date.slice(0, 7)} (${fmt(driest.value, s.key)}, ${severity}).`);
      break; // every area in one grid cell shares this sentence
    }
    lines.push(
      `${s.name}: ${variable} peaks in ${MONTHS[peak.month]} (${fmt(peak.mean, s.key)}${unit(s)}) and is lowest in ${MONTHS[low.month]} (${fmt(low.mean, s.key)}${unit(s)}) in an average year.`,
    );
  }

  if (cycles.length >= 2 && series[0].key !== "spei") {
    const [a, b] = cycles;
    const gaps = a.cycle
      .map((m) => ({ month: m.month, diff: m.mean - (b.cycle.find((n) => n.month === m.month)?.mean ?? NaN) }))
      .filter((g) => !Number.isNaN(g.diff));
    if (gaps.length) {
      const widest = gaps.reduce((x, y) => (Math.abs(y.diff) > Math.abs(x.diff) ? y : x));
      const [higher, lower] = widest.diff > 0 ? [a.s.name, b.s.name] : [b.s.name, a.s.name];
      lines.push(
        `The two areas differ most in ${MONTHS[widest.month]}, when ${higher} is higher than ${lower} by ${fmt(Math.abs(widest.diff), series[0].key)}${unit(a.s)}.`,
      );
    }
  }
  return lines;
}
