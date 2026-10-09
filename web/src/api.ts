export type SeriesPoint = { date: string; ndvi: number | null };

export async function fetchSeries(
  geometry: unknown,
  start: string,
  end: string,
): Promise<SeriesPoint[]> {
  const response = await fetch("/api/series", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ geometry, start, end }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `status ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}
