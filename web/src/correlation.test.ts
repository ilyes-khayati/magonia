import { describe, expect, it } from "vitest";
import type { SeriesPoint } from "./api";
import { anomalies, describeLink, lagCorrelation, monthly, pearson, correlationCautions } from "./correlation";

// Monthly points from 2010-01, one per value
const series = (values: (number | null)[], start = 2010): SeriesPoint[] =>
  values.map((value, i) => ({
    date: `${start + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}-01`,
    value,
    sd: null,
    n_pixels: 1,
    masked: value === null,
    filled: false,
    n_obs: 1,
    n_valid: value === null ? 0 : 1,
  }));

const season = (i: number) => Math.sin((2 * Math.PI * i) / 12);
// Fixed pseudo-random sequences, so the tests are repeatable
function random(seed: number) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 2 ** 32;
    return state / 2 ** 32 - 0.5;
  };
}
const noise = (n: number, seed: number) => Array.from({ length: n }, random(seed));

describe("correlation", () => {
  it("computes Pearson r", () => {
    expect(pearson([1, 2, 3], [2, 4, 6])).toBeCloseTo(1);
    expect(pearson([1, 2, 3], [3, 2, 1])).toBeCloseTo(-1);
    expect(pearson([1, 1, 1], [1, 2, 3])).toBeNaN();
  });

  it("averages several dates in one month and skips masked and filled values", () => {
    const points = [
      { ...series([0.2])[0], date: "2010-01-01" },
      { ...series([0.4])[0], date: "2010-01-17" },
      { ...series([0.9])[0], date: "2010-02-01", filled: true },
    ];
    expect([...monthly(points)]).toEqual([[2010 * 12, expect.closeTo(0.3)]]);
  });

  it("removes the seasonal cycle", () => {
    const flat = anomalies(monthly(series(Array.from({ length: 36 }, (_, i) => 5 + season(i)))));
    for (const v of flat.values()) expect(v).toBeCloseTo(0);
  });

  it("finds the lag at which the driver leads", () => {
    const driver = noise(120, 1);
    const response = driver.map((_, i) => (i >= 3 ? driver[i - 3] : null));
    const lags = lagCorrelation(series(response), series(driver));
    const best = lags.reduce((a, b) => (Math.abs(b.r) > Math.abs(a.r) ? b : a));
    expect(best.lag).toBe(3);
    expect(best.r).toBeCloseTo(1);
  });

  it("does not report a link between two unrelated seasonal series once the cycle is removed", () => {
    const [na, nb] = [noise(120, 1), noise(120, 2)];
    const a = na.map((x, i) => season(i) + 0.2 * x);
    const b = nb.map((x, i) => season(i) + 0.2 * x);
    const raw = lagCorrelation(series(a), series(b), 0, false)[0];
    const clean = lagCorrelation(series(a), series(b), 0, true)[0];
    expect(raw.r).toBeGreaterThan(0.8);
    expect(Math.abs(clean.r)).toBeLessThan(clean.band);
  });

  it("needs at least twelve months in common", () => {
    expect(lagCorrelation(series([1, 2, 3, 4]), series([1, 2, 3, 4]))).toEqual([]);
  });

  it("describes the strongest link in words", () => {
    const lags = [
      { lag: 0, r: 0.1, n: 100, band: 0.196 },
      { lag: 2, r: -0.45, n: 98, band: 0.198 },
    ];
    expect(describeLink("Jendouba", "NDVI", "LST", lags, true)).toBe(
      "Jendouba: NDVI anomalies are most closely linked to LST anomalies from 2 months earlier (r = -0.45): higher LST goes with lower NDVI.",
    );
    expect(describeLink("Sfax", "NDVI", "LST", [{ lag: 1, r: 0.1, n: 100, band: 0.196 }], true)).toMatch(
      /no lag stands out from chance/,
    );
  });
});

describe("guardrails on a correlation", () => {
  const months = (n: number, f: (i: number) => number) =>
    Array.from({ length: n }, (_, i) => ({
      date: `${2010 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}-01`,
      value: f(i),
      sd: null,
      n_pixels: 1,
      masked: false,
      filled: false,
      n_obs: 1,
      n_valid: 1,
    }));
  const season = months(60, (i) => Math.sin((2 * Math.PI * i) / 12) + 0.01 * (i % 5));
  const heat = months(60, (i) => -Math.sin((2 * Math.PI * i) / 12) + 0.01 * (i % 3));

  it("warns when two seasonal series keep their cycle", () => {
    const [caution] = correlationCautions("Orchard", "NDVI", "LST", season, heat, false);
    expect(caution).toMatch(/^Orchard: NDVI and LST both follow a yearly cycle \(\d+% and \d+% of their variance\)/);
    expect(correlationCautions("Orchard", "NDVI", "LST", season, heat, true)).toEqual([]);
  });

  it("warns when there are too few months", () => {
    expect(correlationCautions("Orchard", "NDVI", "LST", season.slice(0, 20), heat.slice(0, 20), true)).toEqual([
      "Orchard: only 20 months in common; a correlation needs about 36 to mean much.",
    ]);
  });
});
