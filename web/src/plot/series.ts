import type { Variable } from "../api";
import type { Entry } from "../components/ChartCard";
import type { TimeSeries } from "./Chart";
import { dateOf } from "./time";

// How a variable is named on an axis and credited under a chart, and an area's series as
// the time charts draw it

export const yLabel = (variable: Variable) => (variable.units ? `${variable.name} (${variable.units})` : variable.name);

export const source = (variable: Variable) => `Source: ${variable.product}${variable.resolution ? ` · ${variable.resolution}` : ""} · Magonia`;

export function timeSeries(shown: Entry[]): TimeSeries[] {
  return shown.map(({ area, colour, state }) => ({
    id: String(area.id),
    name: area.name,
    colour,
    points:
      state?.status === "done"
        ? state.data.points.map((p) => ({
            date: dateOf(p.date),
            value: p.value,
            low: p.value !== null && p.sd !== null ? p.value - p.sd : null,
            high: p.value !== null && p.sd !== null ? p.value + p.sd : null,
            filled: p.filled,
          }))
        : [],
  }));
}
