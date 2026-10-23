// Typed calls to the Magonia API (served under /api by the Vite proxy)

export type Masking = "pixel" | "date" | "none";
export type VariableKey = "ndvi" | "lst" | "spei";
export type Resolution = "native" | "monthly" | "seasonal";

export type Variable = {
  key: VariableKey;
  name: string;
  units: string;
  product: string;
  resolution: string;
  cadence: string;
  scales: number[];
};

export type SeriesPoint = {
  date: string;
  value: number | null;
  sd: number | null;
  n_pixels: number;
  masked: boolean;
  filled: boolean;
  n_obs: number;
  n_valid: number;
};

export type SeriesResponse = {
  variable: VariableKey;
  name: string;
  units: string;
  points: SeriesPoint[];
  warnings: string[];
  provenance: Record<string, unknown>;
};

export type Area = {
  id: number;
  workspace_id: number;
  name: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  area_km2: number;
};

export type WorkspaceSummary = { id: number; name: string; created: string; updated: string };

export type Workspace = WorkspaceSummary & {
  settings: Record<string, unknown>;
  areas: Area[];
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `status ${response.status}`;
    throw new Error(detail);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const fetchCatalogue = () => call<Variable[]>("/catalogue");

export type EarthEngineStatus = { connected: boolean; project: string | null; error: string | null };
export const earthEngineStatus = () => call<EarthEngineStatus>("/earth-engine");
export const setEarthEngineProject = (project: string) =>
  call<EarthEngineStatus>("/earth-engine", send("PUT", { project }));

export const listWorkspaces = () => call<WorkspaceSummary[]>("/workspaces");
export const createWorkspace = (name: string) =>
  call<WorkspaceSummary>("/workspaces", send("POST", { name }));
export const openWorkspace = (id: number) => call<Workspace>(`/workspaces/${id}`);
export const updateWorkspace = (
  id: number,
  change: { name?: string; settings?: Record<string, unknown> },
) => call<Workspace>(`/workspaces/${id}`, send("PATCH", change));

export const createArea = (workspaceId: number, name: string, geometry: unknown) =>
  call<Area>(`/workspaces/${workspaceId}/areas`, send("POST", { name, geometry }));
export const renameArea = (id: number, name: string) =>
  call<Area>(`/areas/${id}`, send("PATCH", { name }));
export const deleteArea = (id: number) => call<void>(`/areas/${id}`, send("DELETE"));

type Job = {
  id: number;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  result: SeriesResponse | null;
};

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export type SeriesOptions = {
  workspace_id: number;
  area_id: number;
  variable: VariableKey;
  start: string;
  end: string;
  masking: Masking;
  scale: number | null;
  resolution: Resolution;
  max_gap: number;
};

// Starts a background job on the API, then asks every second until it finishes
export async function fetchSeries(options: SeriesOptions): Promise<SeriesResponse> {
  let job = await call<Job>("/jobs", send("POST", options));
  while (job.status === "queued" || job.status === "running") {
    await wait(1000);
    job = await call<Job>(`/jobs/${job.id}`);
  }
  if (job.status === "failed" || !job.result) throw new Error(job.error ?? "The job failed.");
  return job.result;
}

// The assistant

export type ChatMessage = { id: number; role: "user" | "assistant"; content: string; created: string };

export const assistantInfo = () => call<{ name: string; model: string }>("/assistant");
export const listMessages = (workspaceId: number) => call<ChatMessage[]>(`/workspaces/${workspaceId}/messages`);
export const clearMessages = (workspaceId: number) =>
  call<void>(`/workspaces/${workspaceId}/messages`, send("DELETE"));

// Sends a question and hands each piece of the answer to onPiece as it arrives
export async function ask(workspaceId: number, content: string, onPiece: (text: string) => void) {
  const response = await fetch(`/api/workspaces/${workspaceId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `status ${response.status}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    onPiece(value);
  }
}
