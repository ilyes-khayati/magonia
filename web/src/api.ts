export type Masking = "pixel" | "date" | "none";

export type SeriesPoint = {
  date: string;
  ndvi: number | null;
  sd: number | null;
  n_pixels: number;
  masked: boolean;
};

export async function fetchSeries(
  geometry: unknown,
  start: string,
  end: string,
  masking: Masking,
): Promise<SeriesPoint[]> {
  const response = await fetch("/api/series", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ geometry, start, end, masking }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `status ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}
