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
// A series split by a wavelet into its slow trend and seasonal part, averaged by month
export type DecompositionResponse = {
  wavelet: string;
  level: number;
  cadence_days: number;
  semi_period_days: number;
  interpolated: number;
  area_id: number;
  points: { date: string; value: number | null; trend: number | null; seasonal: number | null }[];
  summary: string[]; // the sentences Magonia is given about it
};

export const decomposeSeries = (options: SeriesOptions) =>
  call<DecompositionResponse>("/decomposition", send("POST", options));

// How a series remembers itself and which past months of its drivers stand out
export type LagEvidence = {
  driver: string;
  r: number[]; // lags 1 to 12, the driver leading
  bound: number;
  lag: number;
  best: number;
  expected: number | null;
  decision: "stands out" | "not significant" | "implausible sign";
};

export type LagsResponse = { area_id: number; acf: number[]; acf_band: number; drivers: LagEvidence[]; summary: string[] };

export type LagsBody = { response: SeriesOptions; drivers: SeriesOptions[]; deseasonalise: boolean };

export const exploreLags = (body: LagsBody) => call<LagsResponse>("/lags", send("POST", body));

// Models forecasting a series one month ahead, as notebook 04 of the paper fits them
export type FittedModel = {
  name: "Ridge" | "RandomForest" | "XGBoost";
  params: Record<string, unknown>;
  test: { RMSE: number; R2: number; MAE: number };
  seeds: { runs: number; RMSE_mean: number; RMSE_sd: number; R2_mean: number; R2_sd: number };
  rolling: { window: string; RMSE: number; R2: number; MAE: number }[];
  predictions: number[];
};

export type ModelsResponse = {
  features: { name: string; reason: string }[];
  train: [string, string];
  test: [string, string];
  dates: string[];
  observed: number[];
  models: FittedModel[];
  baselines: Record<"persistence" | "climatology", { RMSE: number; R2: number; MAE: number }>;
  summary: string[];
};

export type ModelsBody = {
  response: SeriesOptions;
  drivers: SeriesOptions[];
  own_lags: number[] | null;
  driver_lags: Partial<Record<VariableKey, number[]>> | null;
  test_years: number;
};

// How fitted models explain their inputs, and whether they agree (notebook 05 of the paper)
export type AgreementPair = {
  pair: string;
  tau: number;
  tau_lo: number;
  tau_hi: number;
  dist: number;
  dist_lo: number;
  dist_hi: number;
  separable: boolean | null;
};

export type ExplanationResponse = {
  importance: Record<string, Record<string, number>>;
  families: Record<string, Record<string, number>>;
  agreement: AgreementPair[];
  seeds: number;
  summary: string[];
};

type Running<T> = { status: "running" } | { status: "failed"; error: string } | ({ status: "done" } & T);

// Work that runs in the background on the API: the same request is repeated until it is done
async function poll<T>(path: string, body: unknown, every = 3000): Promise<T> {
  for (;;) {
    const reply = await call<Running<T>>(path, send("POST", body));
    if (reply.status === "done") return reply;
    if (reply.status === "failed") throw new Error(reply.error);
    await new Promise((resolve) => setTimeout(resolve, every));
  }
}

export const fitModels = (body: ModelsBody) => poll<ModelsResponse>("/models", body);
export const explainModels = (body: ModelsBody) => poll<ExplanationResponse>("/explanations", body);

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

export type PaperCard = {
  n: number;
  id: string;
  short: string; // "Sghaier et al., 2022"
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  abstract: string | null;
  open_access_url: string | null;
  cited_by: number;
  countries: string[];
};

export type CitationCheck = { cited: number[]; removed: number[]; unverified: string[] };

// A number in an answer, checked against what the assistant was given. Positions count
// characters (code points), as the engine does.
export type CheckedNumber = {
  start: number;
  end: number;
  text: string;
  status: "verified" | "sign" | "unverified";
  source: string | null;
};

// A closer look the assistant took at the researcher's data
export type Read = { area: string; variable: string; year: number | null };

export type AnswerDetails = {
  searches?: string[];
  papers?: PaperCard[];
  check?: CitationCheck;
  cards?: string[]; // the charts and analyses it was given facts about
  reads?: Read[];
  numbers?: CheckedNumber[];
};

// What is open when a question is asked, so the assistant can discuss it
export type View = {
  page: string;
  charts: VariableKey[];
  resolution: Resolution;
  analyses: unknown[];
  series: SeriesOptions[];
};

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  details: AnswerDetails;
  created: string;
};

export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "search"; query: string }
  | { type: "search_failed"; query: string; error: string }
  | { type: "papers"; papers: PaperCard[] }
  | ({ type: "check"; text: string; numbers?: CheckedNumber[] } & CitationCheck)
  | { type: "error"; message: string }
  | { type: "view"; cards: string[] }
  | ({ type: "read" } & Read);

export const assistantInfo = () => call<{ name: string; model: string }>("/assistant");
export const listMessages = (workspaceId: number) => call<ChatMessage[]>(`/workspaces/${workspaceId}/messages`);
export const clearMessages = (workspaceId: number) =>
  call<void>(`/workspaces/${workspaceId}/messages`, send("DELETE"));

// Sends a question and hands each event to onEvent as it arrives (one JSON object per line)
export async function ask(
  workspaceId: number,
  content: string,
  onEvent: (event: ChatEvent) => void,
  view?: View,
) {
  const response = await fetch(`/api/workspaces/${workspaceId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, view }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `status ${response.status}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let pending = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    pending += value;
    const lines = pending.split("\n");
    pending = lines.pop() ?? "";
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
  }
  if (pending.trim()) onEvent(JSON.parse(pending));
}
