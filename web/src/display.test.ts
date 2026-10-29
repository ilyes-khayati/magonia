import { describe, expect, it } from "vitest";
import type { SeriesPoint } from "./api";
import { anomalies, describeDisplay, display, NO_DISPLAY, smoothed } from "./display";

const point = (date: string, value: number | null, extra: Partial<SeriesPoint> = {}): SeriesPoint => ({
  date,
  value,
  sd: null,
  n_pixels: 1,
  masked: false,
  filled: false,
  n_obs: 1,
  n_valid: 1,
  ...extra,
});
const months = (values: number[], start = 2020) =>
  values.map((v, i) => point(`${start + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}-01`, v));

describe("display", () => {
  it("leaves a straight line unchanged when smoothing, and evens out a spike", () => {
    const line = months([1, 2, 3, 4, 5, 6, 7]);
    expect(smoothed(line).map((p) => p.value)).toEqual([1, 2, 3, 4, 5, 6, 7].map((v) => expect.closeTo(v, 9)));
    const spike = smoothed(months([0, 0, 0, 1, 0, 0, 0]));
    expect(spike[3].value).toBeCloseTo(17 / 35);
  });

  it("subtracts each month's mean over the reference years", () => {
    const series = months([...Array(12).fill(1), ...Array(12).fill(3)]); // 2020 and 2021
    const found = anomalies(series, 2020, 2020).map((p) => p.value);
    expect(found.slice(0, 12)).toEqual(Array(12).fill(0));
    expect(found.slice(12)).toEqual(Array(12).fill(2));
  });

  it("keeps only the chosen months, and says what it shows", () => {
    const d = { smooth: true, anomaly: { from: 2020, to: 2021 }, months: [3, 4, 5] };
    expect(display(months(Array(24).fill(1)), d).map((p) => p.date.slice(5, 7))).toEqual(["03", "04", "05", "03", "04", "05"]);
    expect(describeDisplay(d)).toBe(
      "anomalies against the 2020–2021 mean of each month, smoothed (Savitzky–Golay, 5 points), only Mar, Apr, May",
    );
    expect(describeDisplay(NO_DISPLAY)).toBeNull();
  });

  it("never smooths across masked values", () => {
    const series = months([1, 1, 1, 9, 1, 1, 1]);
    series[3] = { ...series[3], masked: true };
    expect(smoothed(series)[3].value).toBe(9); // a masked value is left as it is, and skipped
  });
});
