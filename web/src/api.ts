// Typed calls to the Magonia API (served under /api by the Vite proxy)

export type Masking = "pixel" | "date" | "none";
export type VariableKey =
  | "ndvi"
  | "savi"
  | "evi"
  | "lai"
  | "fpar"
  | "gpp"
  | "ndmi"
  | "et"
  | "soil_moisture"
  | "nbr"
  | "lst"
  | "air_temperature"
  | "rain"
  | "spei";
export type Resolution = "native" | "monthly" | "seasonal";

export type Variable = {
  key: VariableKey;
  name: string;
  units: string;
  product: string;
  resolution: string;
  cadence: string;
  scales: number[];
  sampling: "mean" | "centre";
  quality: string;
  citation: string;
  group: string;
  learn: Learn | null;
};

// What a researcher needs to know to use a variable well
export type Learn = {
  what: string;
  formula: string;
  reading: string;
  uses: string[];
  limits: string[];
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

export type WorkspaceSummary = {
  id: number;
  name: string;
  created: string;
  updated: string;
  deleted?: string | null; // when it was moved to Recently deleted
};

export type Workspace = WorkspaceSummary & {
  settings: Record<string, unknown>;
  areas: Area[];
};

// FastAPI explains a failure as a string, or, for input it cannot read, as a list of
// { loc, msg } naming each field
export function errorText(body: { detail?: unknown }, status: number): string {
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = (d.loc ?? [])
          .filter((part) => part !== "body" && part !== "query")
          .join(".");
        return field ? `${field}: ${d.msg}` : String(d.msg);
      })
      .join("; ");
  }
  return status >= 500
    ? `Something went wrong on Magonia's side (error ${status}). Try again.`
    : `The request was refused (error ${status}).`;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    // a file upload (FormData) sets its own content type
    headers:
      typeof init?.body === "string"
        ? { "Content-Type": "application/json" }
        : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(errorText(body, response.status));
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const fetchCatalogue = () => call<Variable[]>("/catalogue");

// Variables drawn on the map: one month as tiles, the pixel under a point, an area's pixels

export type Legend = { low: number; high: number; palette: string[] };
export type Tiles = Legend & { url: string; month: string };
export const layerTiles = (
  variable: VariableKey,
  month: string,
  scale?: number,
) =>
  call<Tiles>(
    `/layers/${variable}/tiles?month=${month}${scale ? `&scale=${scale}` : ""}`,
  );
export const layerLegend = (variable: VariableKey) =>
  call<Legend>(`/layers/${variable}/legend`);

export type PointSeries = {
  variable: VariableKey;
  lon: number;
  lat: number;
  name: string;
  units: string;
  pixel_m: number;
  points: { date: string; value: number | null }[];
};
export const inspectPoint = (body: {
  variable: VariableKey;
  lon: number;
  lat: number;
  start: string;
  end: string;
  scale?: number;
}) => call<PointSeries>("/inspect", send("POST", body));

export type PixelGrid = GeoJSON.FeatureCollection & { pixel_m: number };
export const areaPixels = (areaId: number, variable: VariableKey) =>
  call<PixelGrid>(`/areas/${areaId}/pixels?variable=${variable}`);

export type CoherenceResponse = {
  times: string[];
  periods: number[];
  coherence: number[][];
  phase: number[][];
  significant: boolean[][];
  coi: number[];
  summary: string[];
};
export type CoherenceBody = {
  response: SeriesOptions;
  driver: SeriesOptions;
  deseasonalise: boolean;
};
export const coherenceOf = (body: CoherenceBody) =>
  call<CoherenceResponse>("/coherence", send("POST", body));

export type LeakageRow = {
  model: string;
  trend_whole: number;
  trend_causal: number;
  seasonal_whole: number;
  seasonal_causal: number;
  whole: number;
  causal: number;
  raw: number;
};
export type LeakageResponse = {
  test: [string, string];
  rows: LeakageRow[];
  placebo: { whole: number; causal: number };
  baselines: { persistence: number; climatology: number };
  dates: string[];
  observed: number[];
  whole: number[];
  causal: number[];
  best: string;
  summary: string[];
};
export type LeakageBody = { response: SeriesOptions; test_years: number };
export const leakageOf = (body: LeakageBody) =>
  call<LeakageResponse>("/leakage", send("POST", body));

export type PurityPixel = {
  lon: number;
  lat: number;
  share: number;
  amplitude: number;
  error: number;
  inside: boolean;
};
export type PurityResponse = {
  pixels: PurityPixel[];
  perennial: number[];
  seasonal: number[];
  area_cycle: number[];
  area_share: number;
  pixel_m: number;
  summary: string[];
};
export const areaPurity = (body: {
  area: number;
  start: string;
  end: string;
}) =>
  call<PurityResponse>(
    `/areas/${body.area}/purity?start=${body.start}&end=${body.end}`,
  );

export type EarthEngineStatus = {
  connected: boolean;
  project: string | null;
  error: string | null;
};
export const earthEngineStatus = () => call<EarthEngineStatus>("/earth-engine");
export const setEarthEngineProject = (project: string) =>
  call<EarthEngineStatus>("/earth-engine", send("PUT", { project }));

export const listWorkspaces = () => call<WorkspaceSummary[]>("/workspaces");
export const createWorkspace = (name: string) =>
  call<WorkspaceSummary>("/workspaces", send("POST", { name }));
export const openWorkspace = (id: number) =>
  call<Workspace>(`/workspaces/${id}`);
export const updateWorkspace = (
  id: number,
  change: { name?: string; settings?: Record<string, unknown> },
) => call<Workspace>(`/workspaces/${id}`, send("PATCH", change));
// Deleting moves a workspace to Recently deleted for 30 days; from there it can be restored or
// deleted forever
export const deleteWorkspace = (id: number) =>
  call<void>(`/workspaces/${id}`, send("DELETE"));
export const deletedWorkspaces = () =>
  call<WorkspaceSummary[]>("/workspaces?deleted=true");
export const restoreWorkspace = (id: number) =>
  call<WorkspaceSummary>(`/workspaces/${id}/restore`, send("POST"));
export const deleteWorkspaceForever = (id: number) =>
  call<void>(`/workspaces/${id}?forever=true`, send("DELETE"));

export const createArea = (
  workspaceId: number,
  name: string,
  geometry: unknown,
) =>
  call<Area>(
    `/workspaces/${workspaceId}/areas`,
    send("POST", { name, geometry }),
  );
export const renameArea = (id: number, name: string) =>
  call<Area>(`/areas/${id}`, send("PATCH", { name }));
export const deleteArea = (id: number) =>
  call<void>(`/areas/${id}`, send("DELETE"));
export const restoreArea = (id: number) =>
  call<Area>(`/areas/${id}/restore`, send("POST"));

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
  points: {
    date: string;
    value: number | null;
    trend: number | null;
    seasonal: number | null;
  }[];
  summary: string[]; // the sentences Magonia is given about it
  cautions?: string[]; // the guardrails' (AI-03)
};

export const decomposeSeries = (options: SeriesOptions) =>
  call<DecompositionResponse>("/decomposition", send("POST", options));

// The slope of a series' annual means and whether it could be chance (ANA-04)
export type TrendResponse = {
  area_id: number;
  years: Record<string, number>;
  months: string[];
  slope: number | null; // per decade
  intercept: number | null;
  p: number | null;
  change: number | null;
  summary: string[];
  cautions: string[];
};
export const trendOf = (options: SeriesOptions) =>
  call<TrendResponse>("/trend", send("POST", options));

// Start, peak and end of each growing season (ANA-05)
export type Season = {
  year: number;
  start: string;
  peak: string;
  end: string;
  length: number;
  peak_value: number;
  amplitude: number;
};
export type PhenologyResponse = {
  area_id: number;
  seasons: Season[];
  smoothed: { date: string; value: number }[];
  summary: string[];
  cautions: string[];
};
export const phenologyOf = (options: SeriesOptions) =>
  call<PhenologyResponse>("/phenology", send("POST", options));

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

export type LagsResponse = {
  area_id: number;
  acf: number[];
  acf_band: number;
  drivers: LagEvidence[];
  summary: string[];
  cautions?: string[]; // the guardrails' (AI-03)
};

export type LagsBody = {
  response: SeriesOptions;
  drivers: SeriesOptions[];
  deseasonalise: boolean;
};

export const exploreLags = (body: LagsBody) =>
  call<LagsResponse>("/lags", send("POST", body));

// Models forecasting a series one month ahead, tuned and tested by time
export type FittedModel = {
  name: "Ridge" | "RandomForest" | "XGBoost" | "MLP" | "LSTM" | "GRU" | "TCN";
  params: Record<string, unknown>;
  test: { RMSE: number; R2: number; MAE: number };
  seeds: {
    runs: number;
    RMSE_mean: number;
    RMSE_sd: number;
    R2_mean: number;
    R2_sd: number;
  };
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
  baselines: Record<
    "persistence" | "climatology",
    { RMSE: number; R2: number; MAE: number }
  >;
  summary: string[];
  cautions?: string[]; // the guardrails' (AI-03)
};

export type ModelsBody = {
  response: SeriesOptions;
  drivers: SeriesOptions[];
  own_lags: number[] | null;
  driver_lags: Partial<Record<VariableKey, number[]>> | null;
  test_years: number;
  models?: (
    "Ridge" | "RandomForest" | "XGBoost" | "MLP" | "LSTM" | "GRU" | "TCN"
  )[]; // the paper's three when left out
  params?: Partial<
    Record<
      "Ridge" | "RandomForest" | "XGBoost" | "MLP" | "LSTM" | "GRU" | "TCN",
      Record<string, number>
    >
  >; // else tuned
  calendar?: boolean;
  rolling?: boolean;
};

// How fitted models explain their inputs, and whether they agree
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
  family_range?: Record<string, Record<string, [number, number]>>; // share from seed to seed
  dropped?: Record<string, Record<string, number>>; // error rise when a family is left out
  native?: Record<
    string,
    { method: string; importance: Record<string, number>; tau: number }
  >; // each model's own explanation
  timeline?: Record<
    string,
    ({ date: string } & Record<string, number | string>)[]
  >; // month by month, by family
  effects?: Record<string, Record<string, { x: number; effect: number }[]>>; // input → model → accumulated local effects
};

type Running<T> =
  | { status: "running" }
  | { status: "failed"; error: string }
  | ({ status: "done" } & T);

// Work that runs in the background on the API: the same request is repeated until it is done
async function poll<T>(path: string, body: unknown, every = 3000): Promise<T> {
  for (;;) {
    const reply = await call<Running<T>>(path, send("POST", body));
    if (reply.status === "done") return reply;
    if (reply.status === "failed") throw new Error(reply.error);
    await new Promise((resolve) => setTimeout(resolve, every));
  }
}

export const fitModels = (body: ModelsBody) =>
  poll<ModelsResponse>("/models", body);
export const explainModels = (body: ModelsBody) =>
  poll<ExplanationResponse>("/explanations", body);

// What each model leans on when its training years end earlier
export type StabilityResponse = {
  windows: {
    train_end: string;
    families: Record<string, Record<string, number>>;
  }[];
  leading: Record<string, string[]>;
  summary: string[];
};
export const checkStability = (body: ModelsBody) =>
  poll<StabilityResponse>("/stability", body);

export async function fetchSeries(
  options: SeriesOptions,
): Promise<SeriesResponse> {
  let job = await call<Job>("/jobs", send("POST", options));
  while (job.status === "queued" || job.status === "running") {
    await wait(1000);
    job = await call<Job>(`/jobs/${job.id}`);
  }
  if (job.status === "failed" || !job.result)
    throw new Error(job.error ?? "The job failed.");
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
  pdf_url?: string | null; // the open-access PDF itself
  cited_by: number;
  countries: string[];
  relevance?: number | null; // how well it answers the question, from the ranking
  matched?: string[]; // the words it shares with the question
};

export type CitationCheck = {
  cited: number[];
  removed: number[];
  unverified: string[];
  pages_removed?: string[]; // cited pages no passage came from, e.g. "[1, p. 9]"
};

// A statement of the answer that cites papers, and whether those papers say it: supported
// (the model, asked about the closest passage, said yes), unclear, or unsupported
export type SupportCheck = {
  start: number;
  end: number;
  claim: string;
  cites: number[];
  status: "supported" | "unclear" | "unsupported";
  evidence: string; // the closest text from the cited papers
  source: string; // e.g. "[1, p. 6]" or "[2] abstract"
  judged: boolean;
  // for a supported statement: "given" when a passage Magon was given says it, "paper" when
  // one found elsewhere in the paper's full text does
  grounding?: "given" | "paper" | "";
};

// A passage of a paper's full text that Magonia was given, from the paper numbered n
export type PassageCard = { n: number; page: number; text: string };

// Whether a paper was read in full: read, blocked (the publisher refuses downloads),
// unreadable, or abstract only (no open-access PDF)
export type ReadStatus = "read" | "blocked" | "unreadable" | "abstract only";

// A number in an answer, checked against what the assistant was given. Positions count
// characters (code points), as the engine does.
export type CheckedNumber = {
  start: number;
  end: number;
  text: string;
  status: "verified" | "sign" | "elsewhere" | "unverified";
  source: string | null;
};

// A page, button or analysis the answer names, and whether the interface has it
export type AppMention = { start: number; end: number; text: string; kind: string; status: "known" | "unknown" };

// A closer look the assistant took at the researcher's data
export type Read = { area: string; variable: string; year: number | null };

export type AnswerDetails = {
  searches?: string[];
  papers?: PaperCard[];
  check?: CitationCheck;
  cards?: string[]; // the charts and analyses it was given facts about
  reads?: Read[];
  numbers?: CheckedNumber[];
  app?: AppMention[]; // pages, buttons and analyses it named
  proposals?: Proposal[];
  route?: Route;
  passages?: PassageCard[];
  read?: Record<string, ReadStatus>; // by paper number
  support?: SupportCheck[];
  faithfulness?: number | null; // the share of cited statements that are supported
  withdrawn?: SupportCheck[]; // statements taken out because their papers did not support them
  board?: BoardGiven[]; // the pinned items it was given, [B1]…
  board_cited?: number[];
};

// What kind of question code took it for, and so what the answer was allowed to draw on
export type Route = {
  kind: "data" | "research" | "method" | "chat" | "general";
  source: string;
};

// An analysis Magonia proposes; nothing runs until the researcher adds it (AI-07)
export type Proposal = {
  kind:
    | "correlation"
    | "decomposition"
    | "trend"
    | "phenology"
    | "lags"
    | "experiment"
    | "instruction";
  label: string;
  title: string;
  why: string;
  variable?: VariableKey;
  driver?: VariableKey;
  drivers?: VariableKey[];
  area?: string;
  models?: (
    "Ridge" | "RandomForest" | "XGBoost" | "MLP" | "LSTM" | "GRU" | "TCN"
  )[];
  test_years?: number;
  period?: { start: string | null; end: string | null };
  text?: string; // an instruction, in the researcher's words
};

// What is open when a question is asked, so the assistant can discuss it
export type View = {
  page: string;
  charts: VariableKey[];
  resolution: Resolution;
  analyses: unknown[];
  series: SeriesOptions[];
  display?: string | null; // how the Data page shows the series, if changed
  board?: { title: string; text: string; trust: BoardTrust; pinned: string }[]; // what the researcher pinned
  focus?: string | null; // the card asked about ("Ask Magon about this"), by its title
};

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  details: AnswerDetails;
  created: string;
};

// How far Magon may trust a pinned item; a failed answer is never given to it as evidence
export type BoardTrust = "computed" | "checked" | "passage" | "note" | "failed";
export type BoardGiven = { n: number; title: string; trust: BoardTrust; pinned: string };

export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "rewrite"; text: string }
  | { type: "search"; query: string }
  | { type: "search_failed"; query: string; error: string }
  | { type: "papers"; papers: PaperCard[] }
  | ({
      type: "check";
      text: string;
      numbers?: CheckedNumber[];
      app?: AppMention[];
      support?: SupportCheck[];
      faithfulness?: number | null;
      withdrawn?: SupportCheck[];
      board_cited?: number[];
    } & CitationCheck)
  | { type: "board"; items: BoardGiven[] }
  | { type: "verifying" }
  | { type: "error"; message: string }
  | { type: "view"; cards: string[] }
  | ({ type: "read" } & Read)
  | { type: "proposal"; proposal: Proposal }
  | ({ type: "route" } & Route)
  | { type: "reading"; count: number }
  | {
      type: "passages";
      passages: PassageCard[];
      read: Record<string, ReadStatus>;
    };

// The researcher's library: their own PDFs, which Magonia reads and cites like papers
export type LibraryFile = {
  id: string;
  title: string;
  filename: string;
  added: string;
  pages: number;
  pdf?: boolean; // whether the PDF itself is kept, to read it in Magonia
};

// Each workspace has its own files; a file is then reached by its id
export const listFiles = (workspaceId: number) =>
  call<LibraryFile[]>(`/workspaces/${workspaceId}/library`);
export const removeFile = (id: string) =>
  call<void>(`/library/${id}`, send("DELETE"));
export const restoreFile = (id: string) =>
  call<LibraryFile>(`/library/${id}/restore`, send("POST"));
export function addFile(workspaceId: number, file: File) {
  const body = new FormData();
  body.append("file", file);
  return call<LibraryFile & { passages: number }>(
    `/workspaces/${workspaceId}/library`,
    { method: "POST", body },
  );
}

// How the researcher wants Magonia to answer in a workspace
export const getInstructions = (workspaceId: number) =>
  call<{ text: string }>(`/workspaces/${workspaceId}/instructions`);
export const setInstructions = (workspaceId: number, text: string) =>
  call<{ text: string }>(
    `/workspaces/${workspaceId}/instructions`,
    send("PUT", { text }),
  );

export const assistantInfo = () =>
  call<{ name: string; model: string }>("/assistant");

// How Magon answers, chosen in Settings; null keeps the default
export type MagonSettings = {
  model_url: string | null;
  model: string | null;
  temperature: number | null;
  detail: "concise" | "detailed";
  papers_per_search: number;
  search: "keyword" | "hybrid";
  claims: "withdraw" | "mark";
  verifier: "model" | "nli" | "minicheck-roberta" | "minicheck-deberta";
};

export const magonSettings = () =>
  call<
    MagonSettings & {
      // verifier: the checker actually used, the chat model when the chosen one is not installed
      in_use: { model_url: string | null; model: string | null; verifier?: MagonSettings["verifier"] };
    }
  >("/assistant/settings");

export const saveMagonSettings = (settings: MagonSettings) =>
  call<MagonSettings>("/assistant/settings", send("PUT", settings));

export const installedModels = (url?: string) =>
  call<{ models: string[]; error: string | null }>(
    `/assistant/models${url ? `?url=${encodeURIComponent(url)}` : ""}`,
  );

// Conversations with Magonia, several per workspace; a deleted one can be restored for 30 days
export type Conversation = {
  id: number;
  workspace_id: number;
  title: string | null; // null until named: shown as its first question
  first_question: string | null;
  messages: number;
  created: string;
  updated: string;
};

export const listConversations = (workspaceId: number) =>
  call<Conversation[]>(`/workspaces/${workspaceId}/conversations`);
export const createConversation = (workspaceId: number) =>
  call<Conversation>(`/workspaces/${workspaceId}/conversations`, send("POST"));
export const renameConversation = (id: number, title: string) =>
  call<Conversation>(`/conversations/${id}`, send("PATCH", { title }));
export const deleteConversation = (id: number) =>
  call<void>(`/conversations/${id}`, send("DELETE"));
export const restoreConversation = (id: number) =>
  call<Conversation>(`/conversations/${id}/restore`, send("POST"));
export const listMessages = (conversationId: number) =>
  call<ChatMessage[]>(`/conversations/${conversationId}/messages`);

// Sends a question and hands each event to onEvent as it arrives (one JSON object per line)
export async function ask(
  conversationId: number,
  content: string,
  onEvent: (event: ChatEvent) => void,
  view?: View,
) {
  const response = await fetch(`/api/conversations/${conversationId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, view }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(errorText(body, response.status));
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

// An analysis as a Jupyter notebook that reproduces it from the data it used (REP-01)
export type NotebookBody = {
  title: string;
  kind:
    | "experiment"
    | "decomposition"
    | "trend"
    | "phenology"
    | "lags"
    | "correlation"
    | "scales"
    | "coherence"
    | "leakage";
  options: Record<string, unknown>;
  series: SeriesOptions[];
};

export async function downloadNotebook(body: NotebookBody): Promise<void> {
  const notebook = await call<unknown>("/notebook", send("POST", body));
  const link = document.createElement("a");
  link.href = URL.createObjectURL(
    new Blob([JSON.stringify(notebook, null, 1)], {
      type: "application/x-ipynb+json",
    }),
  );
  link.download = `${body.title.replace(/\W+/g, "-").replace(/^-|-$/g, "").toLowerCase() || "magonia"}.ipynb`;
  link.click();
  URL.revokeObjectURL(link.href);
}
