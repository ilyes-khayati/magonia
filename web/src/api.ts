export type Masking = "pixel" | "date" | "none";
export type VariableKey = "ndvi" | "lst";

export type SeriesPoint = {
  date: string;
  value: number | null;
  sd: number | null;
  n_pixels: number;
  masked: boolean;
};

export type SeriesResponse = {
  variable: VariableKey;
  name: string;
  units: string;
  points: SeriesPoint[];
  warnings: string[];
};

export async function fetchSeries(
  geometry: unknown,
  start: string,
  end: string,
  variable: VariableKey,
  masking: Masking,
): Promise<SeriesResponse> {
  const response = await fetch("/api/series", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ geometry, start, end, variable, masking }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `status ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}
