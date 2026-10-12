export type Masking = "pixel" | "date" | "none";
export type VariableKey = "ndvi" | "lst" | "spei";

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

export type Variable = {
  key: VariableKey;
  name: string;
  units: string;
  product: string;
  resolution: string;
  cadence: string;
  scales: number[];
};

export async function fetchCatalogue(): Promise<Variable[]> {
  const response = await fetch("/api/catalogue");
  if (!response.ok) throw new Error(`catalogue: status ${response.status}`);
  return response.json();
}

type Job = {
  id: number;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  result: SeriesResponse | null;
};

async function readJob(response: Response): Promise<Job> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `status ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Starts a background job on the API, then asks every second until it finishes
export async function fetchSeries(
  geometry: unknown,
  start: string,
  end: string,
  variable: VariableKey,
  masking: Masking,
  scale: number | null,
): Promise<SeriesResponse> {
  let job = await readJob(
    await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geometry, start, end, variable, masking, scale }),
    }),
  );
  while (job.status === "queued" || job.status === "running") {
    await wait(1000);
    job = await readJob(await fetch(`/api/jobs/${job.id}`));
  }
  if (job.status === "failed" || !job.result) throw new Error(job.error ?? "The job failed.");
  return job.result;
}
