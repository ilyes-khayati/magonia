import type { Masking, Resolution, SeriesOptions, Variable, VariableKey } from "./api";

// Everything the researcher chooses in the data panel. Saved with the workspace.
export type Settings = {
  variables: VariableKey[];
  scale: number; // SPEI time scale in months
  start: string; // first month, "YYYY-MM"
  end: string; // last month, included
  resolution: Resolution;
  masking: Masking;
  fill: boolean;
  maxGap: number;
  mode: "series" | "seasonal";
};

export const DEFAULTS: Settings = {
  variables: ["ndvi"],
  scale: 12,
  start: "2020-01",
  end: "2024-12",
  resolution: "monthly",
  masking: "pixel",
  fill: true,
  maxGap: 2,
  mode: "series",
};

// A saved workspace may predate a setting, so missing or odd values fall back
export function readSettings(saved: Record<string, unknown> | undefined): Settings {
  const merged = { ...DEFAULTS, ...(saved ?? {}) } as Settings;
  return Array.isArray(merged.variables) ? merged : DEFAULTS;
}

// The month after "YYYY-MM", as the exclusive end date the API expects
function monthAfter(month: string): string {
  const [year, m] = month.split("-").map(Number);
  return m === 12 ? `${year + 1}-01-01` : `${year}-${String(m + 1).padStart(2, "0")}-01`;
}

export function seriesOptions(
  settings: Settings,
  workspaceId: number,
  areaId: number,
  variable: VariableKey,
): SeriesOptions {
  return {
    workspace_id: workspaceId,
    area_id: areaId,
    variable,
    start: `${settings.start}-01`,
    end: monthAfter(settings.end),
    // SPEI has no quality flags, so its cloud filter is fixed
    masking: variable === "spei" ? "none" : settings.masking,
    scale: variable === "spei" ? settings.scale : null,
    resolution: settings.resolution,
    max_gap: settings.fill ? settings.maxGap : 0,
  };
}

// Identical requests share one key, and so one result. The geometry is part of the
// key: an area id alone could later name a different shape.
export const seriesKey = (options: SeriesOptions, geometry: unknown) =>
  JSON.stringify({ ...options, workspace_id: undefined, geometry });

// A variable's name as charts show it; SPEI carries its time scale
export const variableTitle = (v: Variable, settings: Settings) =>
  v.key === "spei" ? `SPEI-${settings.scale}` : v.name;
