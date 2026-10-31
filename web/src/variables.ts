import type { Variable, VariableKey } from "./api";

// Read from one coarse grid cell, without quality flags, so the cloud filter does not apply
export const GRIDDED = new Set<string>(["spei", "rain", "soil_moisture", "air_temperature"]);

// Values of order one or more, such as temperatures and rainfall, written with fewer decimals
export const LARGE = new Set<string>(["lst", "air_temperature", "rain", "gpp", "et"]);

export const large = (key: VariableKey | string) => LARGE.has(key);

// The catalogue in its groups, in the order the catalogue lists them
export function groups(catalogue: Variable[]): [string, Variable[]][] {
  const out = new Map<string, Variable[]>();
  for (const v of catalogue) out.set(v.group || "Other", [...(out.get(v.group || "Other") ?? []), v]);
  return [...out];
}
