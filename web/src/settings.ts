import type { Masking, Resolution, SeriesOptions, Variable, VariableKey } from "./api";
import type { CardLayout } from "./cards";
import { NO_DISPLAY, type Display } from "./display";
import { GRIDDED } from "./variables";

// Everything the researcher chooses in the data panel. Saved with the workspace.
export type Settings = {
  variables: VariableKey[];
  scale: number; // SPEI time scale in months
  scaleByArea: Record<string, number>; // by area id: a SPEI time scale other than scale
  start: string; // first month, "YYYY-MM"
  end: string; // last month, included
  resolution: Resolution;
  masking: Masking;
  fill: boolean;
  maxGap: number;
  mode: "series" | "seasonal" | "distribution";
  cards: Record<string, CardLayout>; // by card: "chart:ndvi", "analysis:3"
  chartOrder: VariableKey[];
  display: Display; // how the Data page shows the series; analyses keep them as extracted
  hiddenAreas: Partial<Record<VariableKey, number[]>>; // by chart: the areas left out of it
};

export const DEFAULTS: Settings = {
  variables: ["ndvi"],
  scale: 12,
  scaleByArea: {},
  start: "2020-01",
  end: "2024-12",
  resolution: "monthly",
  masking: "pixel",
  fill: true,
  maxGap: 2,
  mode: "series",
  cards: {},
  chartOrder: [],
  display: NO_DISPLAY,
  hiddenAreas: {},
};

// A month as "YYYY-MM", or null when the text is not one. Browsers without a month
// picker (Safari) pass on the text as typed, so "2020-1", "2020/01" and "01/2020" are read too.
export function parseMonth(text: string): string | null {
  const t = text.trim();
  const yearFirst = /^(\d{4})[-/.](\d{1,2})$/.exec(t);
  const monthFirst = /^(\d{1,2})[-/.](\d{4})$/.exec(t);
  const [year, month] = yearFirst ? [yearFirst[1], yearFirst[2]] : monthFirst ? [monthFirst[2], monthFirst[1]] : [];
  if (!year || !month || Number(month) < 1 || Number(month) > 12) return null;
  return `${year}-${month.padStart(2, "0")}`;
}

// A saved workspace may predate a setting, so missing or odd values fall back
export function readSettings(saved: Record<string, unknown> | undefined): Settings {
  const merged = { ...DEFAULTS, ...(saved ?? {}) } as Settings;
  // a workspace saved from Safari may hold a month exactly as it was typed
  merged.start = parseMonth(String(merged.start)) ?? DEFAULTS.start;
  merged.end = parseMonth(String(merged.end)) ?? DEFAULTS.end;
  const d = merged.display as Partial<Display> | undefined;
  if (!d || !Array.isArray(d.months)) merged.display = NO_DISPLAY;
  if (typeof merged.hiddenAreas !== "object" || merged.hiddenAreas === null) merged.hiddenAreas = {};
  if (typeof merged.scaleByArea !== "object" || merged.scaleByArea === null) merged.scaleByArea = {};
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
    // gridded climate data have no quality flags, so their cloud filter is fixed
    masking: GRIDDED.has(variable) ? "none" : settings.masking,
    scale: variable === "spei" ? speiScale(settings, areaId) : null,
    resolution: settings.resolution,
    max_gap: settings.fill ? settings.maxGap : 0,
  };
}

// Identical requests share one key, and so one result. The geometry is part of the
// key: an area id alone could later name a different shape.
export const seriesKey = (options: SeriesOptions, geometry: unknown) =>
  JSON.stringify({ ...options, workspace_id: undefined, geometry });

// The SPEI time scale extracted for an area. Areas can differ: a shallow-rooted crop
// may answer to SPEI-3 where a forest answers to SPEI-12.
export const speiScale = (settings: Settings, areaId: number) => settings.scaleByArea[areaId] ?? settings.scale;

// A variable's name as charts show it; SPEI carries its time scale, unless the areas differ
export const variableTitle = (v: Variable, settings: Settings) =>
  v.key !== "spei" ? v.name : Object.keys(settings.scaleByArea).length ? "SPEI" : `SPEI-${settings.scale}`;

// An area's name beside a variable: with a scale per area, SPEI says which one each has
export const areaLabel = (v: Variable, settings: Settings, area: { id: number; name: string }) =>
  v.key === "spei" && Object.keys(settings.scaleByArea).length ? `${area.name} · SPEI-${speiScale(settings, area.id)}` : area.name;
