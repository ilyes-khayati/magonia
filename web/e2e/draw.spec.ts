import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// A small in-memory stand-in for the Magonia API, so the tests need neither the
// API nor Earth Engine
// What the interface sent with each question, for tests to inspect
let library: { id: string; title: string; filename: string; added: string; pages: number }[] = [];
let instructions = "";
let asked: {
  content: string;
  view?: { page: string; charts: string[]; series: { area_id: number; variable: string }[]; display?: string | null };
}[] = [];

// Magon's conversations and their messages, as the fake API keeps them
type FakeConversation = { id: number; workspace_id: number; title: string | null; first_question: string | null; messages: number; created: string; updated: string; deleted?: boolean };
let conversations: FakeConversation[] = [];
let messages: Record<number, { id: number; role: string; content: string; details: object; created: string }[]> = {};

// The series the interface asked to extract
let jobs: { variable: string; resolution: string }[] = [];
let phenologyAsked: { variable: string; resolution: string }[] = [];
let exported: { title: string; kind: string; series: { variable: string }[] }[] = [];
let modelled: {
  response: { variable: string };
  own_lags: number[] | null;
  models?: string[];
  params?: Record<string, Record<string, number>>;
  calendar?: boolean;
}[] = [];
let tilesAsked: { variable: string; month: string }[] = [];
let lagged: { response: { variable: string }; drivers: { variable: string }[]; deseasonalise: boolean }[] = [];

async function fakeApi(page: Page, connected = true) {
  asked = [];
  tilesAsked = [];
  conversations = [];
  messages = {};
  library = [];
  instructions = "";
  modelled = [];
  phenologyAsked = [];
  exported = [];
  jobs = [];
  lagged = [];
  const areas: { id: number; workspace_id: number; name: string; geometry: unknown; area_km2: number }[] = [];
  let settings = {}; // what the interface saved, returned when the workspace is opened again
  await page.route("**/api/catalogue", (route) => route.fulfill({ json: CATALOGUE }));
  await page.route("**/api/earth-engine", (route) =>
    route.request().method() === "PUT"
      ? route.fulfill({ json: { connected: true, project: "my-project", error: null } })
      : route.fulfill({
          json: connected
            ? { connected: true, project: "my-project", error: null }
            : { connected: false, project: null, error: "No Earth Engine project set." },
        }),
  );
  await page.route("**/api/jobs", (route) => {
    jobs.push(route.request().postDataJSON());
    return route.fulfill({ status: 202, json: { id: 1, status: "done", error: null, result: RESULT } });
  });
  await page.route("**/api/layers/*/tiles*", (route) => {
    const url = new URL(route.request().url());
    tilesAsked.push({ variable: url.pathname.split("/")[3], month: url.searchParams.get("month") ?? "" });
    return route.fulfill({
      json: { url: `${url.origin}/api/tile/{z}/{x}/{y}.png`, month: url.searchParams.get("month"), low: 0, high: 0.9, palette: ["#8c510a", "#00441b"] },
    });
  });
  // a transparent pixel for every tile
  await page.route("**/api/tile/**", (route) =>
    route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64") }),
  );
  await page.route("**/api/inspect", (route) => {
    const body = route.request().postDataJSON();
    route.fulfill({
      json: {
        ...body,
        name: "NDVI",
        units: "",
        pixel_m: 250,
        points: Array.from({ length: 24 }, (_, i) => ({ date: `${2023 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}-01`, value: 0.5 + 0.2 * Math.sin(i / 2) })),
      },
    });
  });
  await page.route("**/api/areas/*/pixels*", (route) =>
    route.fulfill({ json: { type: "FeatureCollection", features: [], pixel_m: 250 } }),
  );
  await page.route("**/api/areas/*/purity*", (route) => {
    const pixels = [];
    for (let i = 0; i < 6; i++)
      for (let j = 0; j < 6; j++)
        pixels.push({ lon: 8.548 + i * 0.0025, lat: 36.498 + j * 0.0025, share: (i + j) / 10, amplitude: 0.3, error: 0.01, inside: i > 1 && i < 4 && j > 1 && j < 4 });
    route.fulfill({
      json: {
        pixels,
        perennial: Array(12).fill(0.55),
        seasonal: [0.4, 0.6, 0.8, 0.7, 0.4, 0.2, 0.15, 0.15, 0.2, 0.25, 0.3, 0.35],
        area_cycle: Array(12).fill(0.5),
        area_share: 0.4,
        pixel_m: 231.7,
        summary: ["Orchard: its 4 MODIS pixels are on average 40% annual crop and 60% perennial cover."],
      },
    });
  });
  await page.route("**/api/leakage", (route) => {
    const dates = Array.from({ length: 24 }, (_, i) => `${2023 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
    const wave = dates.map((_, i) => 0.5 + 0.2 * Math.sin(i / 2));
    route.fulfill({
      json: {
        test: ["2023-01", "2024-12"],
        rows: ["Ridge", "RandomForest", "XGBoost"].map((model) => ({ model, trend_whole: 0.99, trend_causal: 0.95, seasonal_whole: 0.8, seasonal_causal: 0.85, whole: 0.05, causal: 0.051, raw: 0.05 })),
        placebo: { whole: 0.99, causal: 0.4 },
        baselines: { persistence: 0.09, climatology: 0.07 },
        dates,
        observed: wave,
        whole: wave,
        causal: wave,
        best: "Ridge",
        summary: ["Orchard: on white noise, where nothing can be forecast, the same recipe reaches trend R² 0.99 with whole-record parts and 0.40 with causal ones."],
      },
    });
  });
  await page.route("**/api/coherence", (route) => {
    const times = Array.from({ length: 48 }, (_, i) => `${2020 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
    const periods = [2, 4, 8, 12, 16];
    route.fulfill({
      json: {
        times,
        periods,
        coherence: periods.map((p) => times.map(() => (p === 12 ? 0.9 : 0.2))),
        phase: periods.map(() => times.map(() => Math.PI)),
        significant: periods.map((p) => times.map(() => p === 12)),
        coi: times.map((_, j) => Math.min(j + 1, 48 - j) * 1.03),
        summary: ["Orchard: at the annual period, NDVI and LST are coherent 100% of the time inside the cone (mean coherence 0.90)."],
      },
    });
  });
  await page.route("**/api/decomposition", (route) => route.fulfill({ json: DECOMPOSITION }));
  await page.route("**/api/phenology", (route) => {
    phenologyAsked.push(route.request().postDataJSON());
    return route.fulfill({
      json: {
        area_id: 1,
        seasons: [
          { year: 2024, start: "2023-11-04", peak: "2024-03-03", end: "2024-05-13", length: 191, peak_value: 0.8, amplitude: 0.45 },
        ],
        smoothed: POINTS.map((p) => ({ date: p.date, value: p.value })),
        summary: ["Orchard, NDVI: over 1 seasons the season starts around 04 Nov, peaks around 03 Mar."],
        cautions: [],
      },
    });
  });
  await page.route("**/api/notebook", (route) => {
    exported.push(route.request().postDataJSON());
    return route.fulfill({ json: { cells: [], metadata: {}, nbformat: 4, nbformat_minor: 5 } });
  });
  await page.route("**/api/trend", (route) =>
    route.fulfill({
      json: {
        area_id: 1,
        years: { "2021": 0.5, "2022": 0.52, "2023": 0.55, "2024": 0.56 },
        months: ["Jan"],
        slope: 0.21,
        intercept: 0.5,
        p: 0.04,
        change: 0.06,
        summary: ["Orchard, NDVI: annual means rising by +0.210 per decade (Sen's slope) over 4 years (2021 to 2024)."],
        cautions: ["Orchard, NDVI: only 4 complete years; a trend test needs about 8 to find anything but a strong trend."],
      },
    }),
  );
  let fitted = false; // the first request starts fitting, the next one finds the result
  await page.route("**/api/models", (route) => {
    modelled.push(route.request().postDataJSON());
    if (!fitted) {
      fitted = true;
      return route.fulfill({ status: 202, json: { status: "running" } });
    }
    return route.fulfill({ json: { status: "done", ...MODELS } });
  });
  let explained = false;
  await page.route("**/api/explanations", (route) => {
    if (!explained) {
      explained = true;
      return route.fulfill({ status: 202, json: { status: "running" } });
    }
    return route.fulfill({ json: { status: "done", ...EXPLANATION } });
  });
  await page.route("**/api/stability", (route) =>
    route.fulfill({
      json: {
        status: "done",
        windows: ["2018-12", "2019-12", "2020-12"].map((train_end, i) => ({
          train_end,
          families: {
            XGBoost: { LST: 0.6, "own history": 0.3 },
            RandomForest: i === 1 ? { LST: 0.4, "own history": 0.57 } : { LST: 0.78, "own history": 0.2 },
            Ridge: { LST: 0.2, "own history": 0.7 },
          },
        })),
        leading: {
          XGBoost: ["LST", "LST", "LST"],
          RandomForest: ["LST", "own history", "LST"],
          Ridge: ["own history", "own history", "own history"],
        },
        summary: ["Orchard: across 3 training windows ending 2018-12 to 2020-12, Random Forest changes what it leans on most."],
      },
    }),
  );
  await page.route("**/api/lags", (route) => {
    lagged.push(route.request().postDataJSON());
    return route.fulfill({ json: LAGS });
  });
  // the first workspace is created when none is found; deleting it moves it to Recently deleted,
  // and the workspace made to replace it is the second
  let deleted: { id: number; name: string; created: string; updated: string; deleted: string }[] = [];
  await page.route("**/api/workspaces", (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: [] });
    const second = deleted.length > 0;
    return route.fulfill({
      status: 201,
      json: { id: second ? 2 : 1, name: second ? "Workspace 2" : "My workspace", created: "", updated: "" },
    });
  });
  await page.route(
    (url) => url.pathname === "/api/workspaces" && url.searchParams.get("deleted") === "true",
    (route) => route.fulfill({ json: deleted }),
  );
  await page.route("**/api/workspaces/2", (route) =>
    route.fulfill({ json: { id: 2, name: "Workspace 2", created: "", updated: "", settings: {}, areas: [], jobs: [] } }),
  );
  await page.route("**/api/workspaces/2/conversations", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/workspaces/1/restore", (route) => {
    deleted = [];
    return route.fulfill({ json: { id: 1, name: "My workspace", created: "", updated: "" } });
  });
  await page.route("**/api/workspaces/1", (route) =>
    route.request().method() === "DELETE"
      ? ((deleted = [{ id: 1, name: "My workspace", created: "", updated: "", deleted: stamp() }]), route.fulfill({ status: 204 }))
      : route.request().method() === "PATCH"
      ? ((settings = route.request().postDataJSON().settings ?? settings), route.fulfill({ json: {} }))
      : route.fulfill({
          json: { id: 1, name: "My workspace", created: "", updated: "", settings, areas, jobs: [] },
        }),
  );
  await page.route("**/api/workspaces/1/library", (route) => {
    if (route.request().method() === "POST") {
      const file = { id: `U${library.length + 1}`, title: "field survey", filename: "field_survey.pdf", added: "2026-10-31 10:00:00", pages: 12, pdf: true };
      library.push(file);
      return route.fulfill({ status: 201, json: { ...file, passages: 30 } });
    }
    return route.fulfill({ json: library });
  });
  let removed: typeof library = [];
  await page.route("**/api/library/*", (route) => {
    removed = library.filter((f) => route.request().url().endsWith(`/${f.id}`));
    library = library.filter((f) => !route.request().url().endsWith(`/${f.id}`));
    return route.fulfill({ status: 204 });
  });
  await page.route("**/api/library/*/restore", (route) => {
    library = [...library, ...removed];
    return route.fulfill({ json: removed[0] });
  });
  await page.route("**/api/library/*/pdf", (route) =>
    route.fulfill({ contentType: "application/pdf", body: Buffer.from("%PDF-1.4\n%%EOF") }),
  );
  await page.route("**/api/workspaces/1/instructions", (route) => {
    if (route.request().method() === "PUT") instructions = route.request().postDataJSON().text;
    return route.fulfill({ json: { text: instructions } });
  });
  await page.route("**/api/assistant", (route) => route.fulfill({ json: { name: "Magon", model: "test model" } }));
  const stamp = () => new Date().toISOString();
  const listed = () =>
    conversations.filter((c) => !c.deleted).sort((a, b) => b.updated.localeCompare(a.updated) || b.id - a.id);
  await page.route("**/api/workspaces/1/conversations", (route) => {
    if (route.request().method() === "POST") {
      const c = { id: conversations.length + 1, workspace_id: 1, title: null, first_question: null, messages: 0, created: stamp(), updated: stamp() };
      conversations.push(c);
      messages[c.id] = [];
      return route.fulfill({ status: 201, json: c });
    }
    return route.fulfill({ json: listed() });
  });
  const conversationOf = (url: string) => conversations.find((c) => url.includes(`/conversations/${c.id}`))!;
  await page.route("**/api/conversations/*", (route) => {
    const c = conversationOf(route.request().url());
    if (route.request().method() === "DELETE") c.deleted = true;
    else c.title = route.request().postDataJSON().title;
    return route.fulfill(route.request().method() === "DELETE" ? { status: 204 } : { json: c });
  });
  await page.route("**/api/conversations/*/restore", (route) => {
    const c = conversationOf(route.request().url());
    c.deleted = false;
    return route.fulfill({ json: c });
  });
  await page.route("**/api/conversations/*/messages", (route) =>
    route.fulfill({ json: messages[conversationOf(route.request().url()).id] }),
  );
  await page.route("**/api/conversations/*/chat", (route) => {
    asked.push(route.request().postDataJSON());
    const question = asked.at(-1)!.content;
    const answer = question.startsWith("From now on")
      ? INSTRUCTING
      : question.startsWith("Propose")
        ? PROPOSING
        : asked.at(-1)!.view?.series.length
          ? DATA_ANSWER
          : ANSWER;
    const c = conversationOf(route.request().url());
    const said = answer.find((e) => e.type === "check") as { text: string } | undefined;
    messages[c.id].push(
      { id: 0, role: "user", content: question, details: {}, created: stamp() },
      { id: 0, role: "assistant", content: said?.text ?? "", details: {}, created: stamp() },
    );
    Object.assign(c, { first_question: c.first_question ?? question, messages: c.messages + 2, updated: stamp() });
    return route.fulfill({
      contentType: "application/x-ndjson",
      body: answer.map((event) => JSON.stringify(event)).join("\n") + "\n",
    });
  });
  await page.route("**/api/workspaces/1/areas", (route) => {
    const body = route.request().postDataJSON();
    const area = { id: areas.length + 1, workspace_id: 1, area_km2: 0.5, ...body };
    areas.push(area);
    return route.fulfill({ status: 201, json: area });
  });
}

const CATALOGUE = [
  { key: "ndvi", name: "NDVI", units: "", product: "MODIS", resolution: "250 m", cadence: "16 days", scales: [] },
  { key: "lst", name: "LST", units: "°C", product: "MODIS", resolution: "1 km", cadence: "8 days", scales: [] },
];

// Two years of monthly NDVI with one filled month, varying a little from year to year
const POINTS = Array.from({ length: 24 }, (_, i) => ({
  date: `${2023 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}-01`,
  value: 0.3 + 0.4 * Math.max(0, Math.cos(((i % 12) - 2) / 2)) + 0.01 * ((i * 7) % 5),
  sd: 0.05,
  n_pixels: 18,
  masked: i === 5,
  filled: i === 5,
  n_obs: 2,
  n_valid: i === 5 ? 0 : 2,
}));

const RESULT = {
  variable: "ndvi",
  name: "NDVI",
  units: "",
  points: POINTS,
  warnings: [],
  provenance: {
    id: "7fd36665e815857e",
    variable: { product: "MODIS Terra MOD13Q1 v6.1", band: "NDVI", licence: "open", citation: "Didan 2021" },
    area: { area_km2: 0.5, sampling: "area-weighted mean" },
    window: { start: "2023-01-01", end: "2025-01-01" },
    steps: [{ step: "fill gaps", method: "linear interpolation in time", filled: 1 }],
  },
};

const DECOMPOSITION = {
  wavelet: "dmey",
  level: 5,
  cadence_days: 16,
  semi_period_days: 381,
  interpolated: 3,
  area_id: 1,
  points: POINTS.map((p, i) => ({ date: p.date, value: p.value, trend: 0.45 + i * 0.001, seasonal: p.value - 0.45 - i * 0.001 })),
  summary: [
    "Orchard, NDVI: the trend went from 0.45 (2023 mean) to 0.47 (2024 mean); lowest 0.45 in 2023-01, highest 0.47 in 2024-12.",
    "Orchard, NDVI: the seasonal part carries 96% of the variation and the trend 4%; the seasonal part swings by 0.40 within a year on average.",
  ],
};

const LAGS = {
  area_id: 1,
  acf: Array.from({ length: 24 }, (_, i) => 0.7 * 0.8 ** i),
  acf_band: 0.11,
  drivers: [
    {
      driver: "LST",
      r: Array.from({ length: 12 }, (_, i) => (i === 0 ? -0.42 : -0.05)),
      bound: 0.22,
      lag: 1,
      best: -0.42,
      expected: -1,
      decision: "stands out",
    },
  ],
  summary: [
    "Orchard: NDVI anomalies remember themselves at 12 of 24 lags beyond chance (±0.11); at 1 month r = 0.70.",
    "Orchard: LST 1 month earlier is the strongest of lags 1 to 12 (r = -0.42, bound ±0.22); it stands out with the expected sign.",
  ],
};

const fitted = (name: string, rmse: number, sd: number) => ({
  name,
  params: {},
  test: { RMSE: rmse, R2: 0.86, MAE: rmse * 0.7 },
  seeds: { runs: name === "Ridge" ? 1 : 20, RMSE_mean: rmse, RMSE_sd: sd, R2_mean: 0.86, R2_sd: 0.002 },
  rolling: [{ window: "2019-2021", RMSE: rmse - 0.005, R2: 0.9, MAE: 0.03 }, { window: "2022-2024", RMSE: rmse, R2: 0.86, MAE: 0.04 }],
  predictions: POINTS.slice(12).map((p) => p.value + 0.01),
});

const MODELS = {
  features: [
    { name: "NDVI lag 1", reason: "autocorrelation beyond chance (±0.11), strongest first" },
    { name: "calendar month", reason: "the seasonal cycle, as sine and cosine" },
  ],
  train: ["2002-03", "2023-12"],
  test: ["2024-01", "2024-12"],
  dates: POINTS.slice(12).map((p) => p.date),
  observed: POINTS.slice(12).map((p) => p.value),
  models: [fitted("Ridge", 0.0584, 0), fitted("RandomForest", 0.0558, 0.0004), fitted("XGBoost", 0.0563, 0.0006)],
  baselines: { persistence: { RMSE: 0.0972, R2: 0.62, MAE: 0.07 }, climatology: { RMSE: 0.0753, R2: 0.77, MAE: 0.05 } },
  summary: ["Orchard: lowest test error Random Forest (RMSE 0.0558, R² 0.87), then XGBoost 0.0563, Ridge 0.0584."],
};

const EXPLANATION = {
  importance: {},
  families: {
    XGBoost: { "own history": 0.38, LST: 0.61, calendar: 0.01 },
    RandomForest: { "own history": 0.55, LST: 0.44, calendar: 0.01 },
    Ridge: { "own history": 0.94, LST: 0.05, calendar: 0.01 },
  },
  agreement: [],
  seeds: 5,
  family_range: { XGBoost: { LST: [0.58, 0.65] } },
  dropped: { XGBoost: { LST: 0.18, "own history": 0.4 }, RandomForest: { LST: 0.05 }, Ridge: { LST: -0.01 } },
  summary: [
    "Orchard: XGBoost and Ridge explain the data differently, beyond what refitting with another seed changes (weighted τ 0.46, against at least 0.89 for a model with itself; 67% of the importance would have to move).",
  ],
};

const paper = (n: number, short: string, title: string) => ({
  n,
  id: `W${n}`,
  short,
  title,
  authors: [],
  year: 2022,
  venue: "Journal of Agricultural Engineering",
  doi: `10.1/${n}`,
  abstract: "Drought stress was mapped in rainfed olive groves.",
  open_access_url: null,
  cited_by: 12,
  countries: ["TN"],
});

// An answer that searched, found two papers, and cited one real paper and one invented number
const ANSWER = [
  { type: "search", query: "olive drought NDVI" },
  {
    type: "papers",
    papers: [paper(1, "Sghaier et al., 2022", "Drought stress in arid olive groves"), paper(2, "Crespo et al., 2025", "Olive VI and drought")],
  },
  { type: "reading", count: 1 },
  {
    type: "passages",
    read: { "1": "read", "2": "blocked" },
    passages: [{ n: 1, page: 6, text: "Rainfed groves lost NDVI within one season of drought." }],
  },
  { type: "text", text: "Drought lowers olive NDVI [1, p. 6], as also shown in [7]." },
  {
    type: "check",
    text: "Drought lowers olive NDVI [1, p. 6], as also shown in.",
    cited: [1],
    removed: [7],
    unverified: [],
    pages_removed: [],
    faithfulness: 0.5,
    support: [
      {
        start: 0,
        end: 37,
        claim: "Drought reduces the greenness of olive groves.",
        cites: [1],
        status: "supported",
        evidence: "Rainfed groves lost NDVI within one season of drought.",
        source: "[1, p. 6]",
        judged: true,
      },
      {
        start: 38,
        end: 55,
        claim: "Irrigation stops the decline entirely.",
        cites: [1],
        status: "unsupported",
        evidence: "Rainfed groves lost NDVI within one season of drought.",
        source: "[1, p. 6]",
        judged: true,
      },
    ],
  },
];

// An instruction asked for in the chat: proposed, saved only on a click
const INSTRUCTING = [
  {
    type: "proposal",
    proposal: {
      kind: "instruction",
      label: "instruction",
      title: "Answer in French.",
      why: "Kept for every question in this workspace; edit it on the Library page.",
      text: "Answer in French.",
    },
  },
  { type: "text", text: "Save it below and I will answer in French." },
  { type: "check", text: "Save it below and I will answer in French.", cited: [], removed: [], unverified: [] },
];

// An answer about the researcher's own data, after a closer look at one year
const DATA_ANSWER = [
  { type: "view", cards: ["NDVI chart"] },
  { type: "read", area: "Orchard", variable: "ndvi", year: 2024 },
  { type: "text", text: "Orchard NDVI peaks in Aug (0.70) (NDVI chart), and was 0.95 in 2024." },
  {
    type: "check",
    text: "Orchard NDVI peaks in Aug (0.70) (NDVI chart), and was 0.95 in 2024.",
    cited: [],
    removed: [],
    unverified: [],
    numbers: [
      { start: 27, end: 31, text: "0.70", status: "verified", source: "NDVI chart" },
      { start: 55, end: 59, text: "0.95", status: "unverified", source: null },
      { start: 63, end: 67, text: "2024", status: "verified", source: "reading Orchard NDVI 2024" },
    ],
  },
];

const SQUARE = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Orchard" },
      geometry: {
        type: "Polygon",
        coordinates: [[[8.55, 36.5], [8.56, 36.5], [8.56, 36.51], [8.55, 36.51], [8.55, 36.5]]],
      },
    },
  ],
};

test.beforeEach(async ({ page }, info) => {
  await fakeApi(page, !info.title.includes("not connected"));
  await page.goto("/");
  await expect(page.locator(".map[data-ready=true]")).toBeVisible();
});

test("drawing a polygon saves it as an area", async ({ page }) => {
  await page.getByRole("button", { name: "Draw a polygon" }).click();
  const map = page.locator(".map");
  for (const [x, y] of [[300, 300], [450, 300], [450, 420], [300, 420], [300, 300]]) {
    await map.click({ position: { x, y } });
  }
  await expect(page.getByRole("toolbar").getByRole("button", { name: /^Area 1/ })).toBeVisible();
});

test("uploading a GeoJSON file adds its named areas", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await expect(page.getByRole("toolbar").getByRole("button", { name: /^Orchard/ })).toBeVisible();
  await expect(page.getByText("Added 1 area from fields.geojson.")).toBeVisible();
});

test("Magon's model and answers are chosen in Settings", async ({ page }) => {
  const saved: unknown[] = [];
  await page.route("**/api/assistant/settings", (route) => {
    if (route.request().method() === "PUT") {
      saved.push(route.request().postDataJSON());
      return route.fulfill({ json: route.request().postDataJSON() });
    }
    return route.fulfill({
      json: {
        model_url: null,
        model: null,
        temperature: null,
        detail: "concise",
        papers_per_search: 6,
        in_use: { model_url: "http://localhost:11434", model: "qwen2.5:7b" },
      },
    });
  });
  await page.route("**/api/assistant/models*", (route) =>
    route.fulfill({ json: { models: ["qwen2.5:7b", "qwen3:8b"], error: null } }),
  );
  await page.getByRole("button", { name: "Settings" }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await settings.getByLabel("Language model").selectOption("qwen3:8b");
  await settings.getByRole("button", { name: "Detailed" }).click();
  await settings.getByRole("button", { name: "Precise" }).click();
  await settings.getByLabel("Papers read per search").selectOption("8");
  await settings.getByRole("button", { name: "Save" }).click();
  await expect(settings.getByText("Saved")).toBeVisible();
  expect(saved).toEqual([{ model_url: null, model: "qwen3:8b", temperature: 0.2, detail: "detailed", papers_per_search: 8 }]);
});

test("the theme can be switched to dark", async ({ page }) => {
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Appearance" }).click();
  await page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("an area with NDVI chosen shows its chart, statistics, provenance and summary", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  const chart = page.getByRole("region", { name: "NDVI chart" });
  await expect(chart.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await expect(chart.getByRole("rowheader", { name: "Orchard" })).toBeVisible();
  await chart.getByRole("button", { name: "Where this comes from" }).click();
  await expect(chart.getByText("7fd36665e815857e")).toBeVisible();
  await expect(page.getByText(/Orchard: NDVI peaks in/)).toBeVisible();
  await page.getByRole("button", { name: "Seasonal cycle" }).click();
  await expect(chart.getByText("Average year", { exact: false })).toBeVisible();
});

test("a correlation is shown only once added, and is saved with the workspace", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("region", { name: "Suggested analyses" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Correlation chart" })).toHaveCount(0);

  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Correlation and lag/ }).click();
  const card = page.getByRole("region", { name: "Correlation chart" });
  await expect(card.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  // the fake API returns the same series for both variables, so they match in the same month
  await expect(card.getByText(/Orchard: NDVI anomalies are most closely linked to LST anomalies from the same month \(r = 1\.00\)/)).toBeVisible();

  await card.getByRole("checkbox", { name: "Remove seasonal cycle" }).uncheck();
  await expect(card.getByRole("list", { name: "Cautions" })).toContainText("months in common"); // a guardrail
  await page.waitForTimeout(700); // saving waits half a second after the last change
  await page.reload();
  await expect(card.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await expect(card.getByRole("checkbox", { name: "Remove seasonal cycle" })).not.toBeChecked();

  await card.getByRole("button", { name: "Remove this analysis" }).click();
  await expect(page.getByRole("region", { name: "Suggested analyses" })).toBeVisible();

  // nothing is lost by one click: Undo brings it back as it was, and so does ⌘Z
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect(card.getByRole("checkbox", { name: "Remove seasonal cycle" })).not.toBeChecked();
  await card.getByRole("button", { name: "Remove this analysis" }).click();
  await expect(card).toHaveCount(0);
  await page.keyboard.press("ControlOrMeta+z");
  await expect(card.locator('.plot-svg [data-mark="line"]')).toBeVisible();
});

test("an analysis fetches its variables even when they are not charted", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Correlation and lag/ }).click();
  const card = page.getByRole("region", { name: "Correlation chart" });
  await expect(card.getByRole("combobox", { name: "Driver" })).toHaveValue("lst");
  await expect(card.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await expect(page.getByRole("checkbox", { name: /LST/ })).not.toBeChecked();
});

test("a decomposition asks for the series at its own time step and shows trend and season", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Trend and season/ }).click();

  const card = page.getByRole("region", { name: "Decomposition chart" });
  await expect(card.getByText("Discrete Meyer wavelet, level 5 on 16-day steps")).toBeVisible();
  await expect(card.locator('.plot-svg [data-mark="line"]')).toHaveCount(3); // value and trend above, season below
  await expect(card.getByText(/the trend went from 0.45 \(2023 mean\)/)).toBeVisible();
  await expect(card.getByText(/not a forecast\. 3 empty dates were filled/)).toBeVisible();
  expect(jobs.some((j) => j.variable === "ndvi" && j.resolution === "native")).toBe(true);

  const results = await new AxeBuilder({ page }).include("[aria-label='Decomposition chart']").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => v.id)).toEqual([]);
});

test("a trend card tests the annual means and warns about short records", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /rising or falling/ }).click();
  const card = page.getByRole("region", { name: "Trend chart" });
  await expect(card.getByRole("row", { name: /Orchard/ })).toContainText("+0.210");
  await expect(card.getByRole("row", { name: /Orchard/ })).toContainText("significant");
  await expect(card.getByRole("list", { name: "Cautions" })).toContainText("Only 4 complete years");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Long-term trend as a notebook" }).click();
  expect((await download).suggestedFilename()).toBe("long-term-trend.ipynb");
  expect(exported.at(-1)).toMatchObject({ kind: "trend", series: [{ variable: "ndvi" }] });
  const results = await new AxeBuilder({ page }).include("[aria-label='Trend chart']").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("an analysis can be duplicated and renamed, and keeps its name", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /rising or falling/ }).click();
  await page.getByRole("button", { name: "Duplicate Long-term trend" }).click();
  const cards = page.getByRole("region", { name: "Trend chart" });
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(1).getByRole("heading", { name: "Long-term trend (copy)" })).toBeVisible();

  await cards.nth(0).getByRole("heading", { name: "Long-term trend" }).dblclick();
  await page.getByRole("textbox", { name: "New name for Long-term trend" }).fill("Drought years");
  await page.getByRole("textbox", { name: "New name for Long-term trend" }).press("Enter");
  await expect(cards.nth(0).getByRole("heading", { name: "Drought years" })).toBeVisible();
  await page.waitForTimeout(700); // saving waits half a second after the last change
  await page.reload();
  await expect(cards.nth(0).getByRole("heading", { name: "Drought years" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Duplicate Drought years" })).toBeVisible();
});

test("season dates are found from NDVI at its own time step", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /season start, peak and end/ }).click();
  const card = page.getByRole("region", { name: "Season dates chart" });
  await expect(card.getByRole("row", { name: /2024/ })).toContainText("2023-11-04");
  await expect(card.getByText(/starts around 04 Nov/)).toBeVisible();
  expect(phenologyAsked.at(-1)).toMatchObject({ variable: "ndvi", resolution: "native" });
  const results = await new AxeBuilder({ page }).include("[aria-label='Season dates chart']").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("the lag explorer tests drivers and says which stand out", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Memory and lags/ }).click();

  const card = page.getByRole("region", { name: "Lags chart" });
  await expect(card.getByText("LST: stands out")).toBeVisible();
  await expect(card.getByText(/it stands out with the expected sign/)).toBeVisible();
  await expect(card.locator('.plot-svg [data-mark="bar"] rect')).toHaveCount(24);
  expect(lagged.at(-1)?.response.variable).toBe("ndvi");
  expect(lagged.at(-1)?.drivers.map((d) => d.variable)).toEqual(["lst", "spei"]);

  await card.getByRole("checkbox", { name: "Remove seasonal cycle" }).uncheck();
  await expect.poll(() => lagged.at(-1)?.deseasonalise).toBe(false);

  const results = await new AxeBuilder({ page }).include("[aria-label='Lags chart']").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => v.id)).toEqual([]);
});

test("an experiment runs a recipe, keeps its results, and two runs can be compared", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Model" }).click();
  await page.getByRole("region", { name: "Suggested experiments" }).getByRole("button", { name: /New experiment/ }).click();

  const experiment = page.getByRole("region", { name: "Experiment" });
  // nothing is chosen for the researcher: no model, no driver, no calendar
  await expect(experiment.getByRole("button", { name: "Run experiment" })).toBeDisabled();
  for (const name of ["Ridge", "Random Forest", "XGBoost", /^LST$/, /Calendar month/]) {
    await expect(experiment.getByRole("checkbox", { name })).not.toBeChecked();
    await experiment.getByRole("checkbox", { name }).check();
  }
  expect(modelled).toHaveLength(0); // nothing runs before it is asked for
  await experiment.getByRole("button", { name: "Run experiment" }).click();
  await expect(experiment.getByText(/Tuning the models/)).toBeVisible();
  const table = experiment.getByRole("table", { name: "Test scores of each model and baseline" });
  await expect(table).toBeVisible({ timeout: 10_000 });
  await expect(table.getByRole("rowheader")).toHaveText([
    "Random Forest",
    "XGBoost",
    "Ridge",
    "Persistence (last month)",
    "Climatology (usual month)",
  ]);
  await expect(table.getByRole("row", { name: /Random Forest/ })).toContainText("±0.0004");
  expect(modelled.at(-1)).toMatchObject({ own_lags: null, test_years: 3 });
  expect(modelled.at(-1)).not.toHaveProperty("models"); // all three models: the plain request

  await experiment.getByRole("button", { name: "Explain the models" }).click();
  const families = experiment.getByRole("table", { name: "Share of each model's importance by family of inputs" });
  await expect(families).toBeVisible({ timeout: 10_000 });
  await expect(families.getByRole("row", { name: /LST/ })).toContainText("61% 58–65");
  const dropped = experiment.getByRole("table", { name: "Refitted without it: how much the error rises" });
  await expect(dropped.getByRole("row", { name: /LST/ })).toContainText("+18%");
  await expect(dropped.getByRole("row", { name: /LST/ })).toContainText("−1%");
  await expect(experiment.getByText(/XGBoost and Ridge explain the data differently/)).toBeVisible();
  await experiment.getByRole("button", { name: "Check across training windows" }).click();
  const held = experiment.getByRole("table", { name: "What each model leans on most, by training window" });
  await expect(held.getByRole("row", { name: /2019-12/ })).toContainText("own history 57%");
  await expect(experiment.getByText(/Random Forest changes what it leans on most/)).toBeVisible();

  // the explanation is kept with the experiment, so it is back after a reload
  await page.waitForTimeout(700);
  await page.reload();
  await expect(families).toBeVisible({ timeout: 10_000 });

  // pinned, the run is live on the board: its scores and explanations, not a picture
  await experiment.getByRole("button", { name: "Pin", exact: true }).click();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Board" }).click();
  const pinned = page.getByRole("region", { name: "Experiment 1" });
  await expect(pinned.getByRole("table", { name: "Test scores of each model and baseline" })).toBeVisible();
  await expect(pinned.getByRole("table", { name: "Share of each model's importance by family of inputs" })).toBeVisible();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Model" }).click();

  // a copy with one change, then the two side by side
  await experiment.getByRole("button", { name: "Duplicate" }).click();
  await experiment.getByRole("checkbox", { name: "Ridge" }).uncheck();
  await experiment.getByRole("group", { name: "XGBoost hyperparameters" }).getByRole("button", { name: "Manual" }).click();
  await experiment.getByRole("spinbutton", { name: "Maximum depth" }).first().fill("3");
  await experiment.getByRole("spinbutton", { name: "Maximum depth" }).first().blur();
  await experiment.getByRole("checkbox", { name: /Calendar month/ }).uncheck();
  await experiment.getByRole("button", { name: "Run experiment" }).click();
  await expect.poll(() => modelled.at(-1)?.models).toEqual(["RandomForest", "XGBoost"]);
  expect(modelled.at(-1)).toMatchObject({ calendar: false });
  expect(modelled.at(-1)?.params?.XGBoost).toEqual({ max_depth: 3 });

  const list = page.getByRole("navigation", { name: "Experiments" });
  await list.getByRole("checkbox", { name: "Compare" }).nth(0).check();
  await list.getByRole("checkbox", { name: "Compare" }).nth(1).check();
  const comparison = page.getByRole("region", { name: "Comparison" });
  await expect(comparison.getByText(/calendar only in the first; models Ridge, Random Forest, XGBoost against Random Forest, XGBoost/)).toBeVisible();
  await expect(comparison.getByRole("table", { name: "Test scores of each model and baseline" })).toHaveCount(2);

  const results = await new AxeBuilder({ page }).include(".model-page").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});

test("when Earth Engine is not connected, the setup explains how and saves the project", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "Connect Google Earth Engine" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Project id").fill("my-project");
  await dialog.getByRole("button", { name: "Connect" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Settings" }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await settings.getByRole("button", { name: "Earth Engine" }).click();
  await expect(settings).toContainText("Connected");
  await expect(settings).toContainText("my-project");
});

test("the workspace is named at the head of the rail and can be renamed", async ({ page }) => {
  const renamed: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "PATCH" && r.url().endsWith("/workspaces/1") && r.postDataJSON().name) renamed.push(r.postDataJSON().name);
  });
  const menu = page.getByRole("button", { name: /^Workspace: My workspace/ });
  await menu.click();
  await page.getByRole("group", { name: "Workspaces" }).getByRole("button", { name: "Rename this workspace…" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("Jendouba orchard");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Workspace: Jendouba orchard/ })).toBeVisible();
  expect(renamed).toEqual(["Jendouba orchard"]);
});

test("a deleted workspace can be brought back, at once or from Recently deleted", async ({ page }) => {
  const banner = page.getByRole("navigation", { name: "Pages" });
  const workspaces = page.getByRole("group", { name: "Workspaces" });
  await banner.getByRole("button", { name: /My workspace/ }).click();
  await workspaces.getByRole("button", { name: "Delete this workspace" }).click();
  // the only workspace is replaced by a new one, and the deletion can be undone
  await expect(page).toHaveURL(/\/workspaces\/2\//);
  await expect(page.getByRole("status")).toContainText("My workspace moved to Recently deleted");
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect(page).toHaveURL(/\/workspaces\/1\//);
  await expect(banner.getByRole("button", { name: /My workspace/ })).toBeVisible();

  await banner.getByRole("button", { name: /My workspace/ }).click();
  await workspaces.getByRole("button", { name: "Delete this workspace" }).click();
  await expect(page).toHaveURL(/\/workspaces\/2\//);
  await banner.getByRole("button", { name: /Workspace 2/ }).click();
  await workspaces.getByRole("button", { name: "Recently deleted…" }).click();
  await expect(workspaces).toContainText("My workspace · deleted today");
  await workspaces.getByRole("button", { name: "Restore" }).click();
  await expect(page).toHaveURL(/\/workspaces\/1\//);
});

test("a new conversation keeps the earlier ones, which can be reopened, renamed and deleted", async ({ page }) => {
  const assistant = page.getByRole("region", { name: "Magon" });
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();

  const list = assistant.getByRole("group", { name: "Conversations" });
  await assistant.getByRole("button", { name: "Conversations" }).click();
  await list.getByRole("button", { name: "New conversation" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toHaveCount(0);
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What is NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await expect(assistant.getByText("What does drought do to olive NDVI?")).toHaveCount(0);

  // both are kept, named by their first question until renamed
  await assistant.getByRole("button", { name: "Conversations" }).click();
  await expect(list.getByRole("listitem")).toHaveCount(2);
  await list.getByRole("button", { name: "Rename What does drought do to olive NDVI?" }).click();
  await list.getByRole("textbox", { name: "Name of the conversation" }).fill("Drought");
  await list.getByRole("textbox", { name: "Name of the conversation" }).press("Enter");
  await list.getByRole("button", { name: /^Drought/ }).first().click();
  await expect(assistant.getByText("What does drought do to olive NDVI?")).toBeVisible();
  await expect(assistant.getByRole("button", { name: "Conversations" })).toHaveText("Drought");

  // deleting one opens the other, and Undo brings it back
  await assistant.getByRole("button", { name: "Conversations" }).click();
  await list.getByRole("button", { name: "Delete Drought" }).click();
  await expect(assistant.getByRole("button", { name: "Conversations" })).toHaveText("What is NDVI?");
  await page.getByRole("status").filter({ hasText: "deleted" }).getByRole("button", { name: "Undo" }).click();
  await expect(assistant.getByRole("button", { name: "Conversations" })).toHaveText("Drought");
  // the panel stays open, on the conversation open last
  await page.reload();
  await expect(assistant.getByRole("button", { name: "Conversations" })).toHaveText("Drought");
});

test("Magonia's panel can be widened by its edge, and stays open across pages", async ({ page }) => {
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Magon" });
  const before = (await panel.boundingBox())!.width;
  const edge = page.getByRole("separator", { name: "Resize Magon's panel" });
  await edge.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await panel.boundingBox())!.width).toBe(before + 80);
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("region", { name: "Magon" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Magon" })).toBeVisible();
  await expect.poll(async () => (await panel.boundingBox())!.width).toBe(before + 80);
});

test("empty pages suggest what to add", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("complementary", { name: "Data" }).getByRole("checkbox", { name: /NDVI/ }).uncheck();
  const charts = page.getByRole("region", { name: "Suggested charts" });
  await charts.getByRole("button", { name: /LST/ }).click();
  await expect(page.getByRole("region", { name: "LST chart" })).toBeVisible();
  await expect(charts).toHaveCount(0);

  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByText(/^Data: Jan 2020 to Dec 2024 · monthly/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Add analysis" })).toHaveCount(0);
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Which past months matter/ }).click();
  await expect(page.getByRole("region", { name: "Lags chart" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Suggested analyses" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add analysis" })).toBeVisible();
});

test("cards can be moved, widened and folded, and stay so", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  const titles = page.locator(".page-grid .card h3");
  await expect(titles).toHaveText(["NDVI", "LST"]);

  await page.getByRole("button", { name: "Move LST" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(titles).toHaveText(["LST", "NDVI"]);
  await expect(page.getByRole("button", { name: "Move LST" })).toBeFocused();
  await page.getByRole("button", { name: "Move LST" }).hover();
  await page.mouse.down();
  const target = (await page.getByRole("region", { name: "NDVI chart" }).boundingBox())!;
  // near the card's title: a tall card's middle can be below the window
  await page.mouse.move(target.x + target.width / 2, target.y + 30, { steps: 8 });
  await page.mouse.up();
  await expect(titles).toHaveText(["NDVI", "LST"]);

  await page.getByRole("button", { name: "Full width: NDVI" }).click();
  const ndvi = page.getByRole("region", { name: "NDVI chart" });
  const lst = page.getByRole("region", { name: "LST chart" });
  await expect(page.locator(".slot", { has: ndvi })).toHaveAttribute("data-wide", "true"); // spans every column
  await page.getByRole("button", { name: "Show LST" }).click();
  await expect(lst.locator(".plot-svg")).toBeHidden();
  await expect(lst.getByRole("heading", { name: "LST" })).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save NDVI as an image" }).click();
  const image = await download;
  expect(image.suggestedFilename()).toBe("ndvi.png");
  const bytes = await (await import("node:fs/promises")).readFile((await image.path())!);
  expect([...bytes.subarray(1, 4)].map((b) => String.fromCharCode(b)).join("")).toBe("PNG");

  await page.waitForTimeout(700); // saving waits half a second after the last change
  await page.reload();
  await expect(titles).toHaveText(["NDVI", "LST"]);
  await expect(page.getByRole("button", { name: "Show LST" })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: "Full width: NDVI" })).toHaveAttribute("aria-pressed", "true");
});

test("the Data page can smooth, show anomalies and keep some months, without asking again", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  const chart = page.getByRole("region", { name: "NDVI chart" });
  await expect(chart.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  const extracted = jobs.length;
  const panel = page.getByRole("complementary", { name: "Data" });
  await panel.getByRole("checkbox", { name: "Smooth" }).check();
  await panel.getByRole("checkbox", { name: "Anomalies" }).check();
  await panel.getByRole("button", { name: "January" }).click();
  await expect(chart.getByText(/anomalies against the 2020–2024 mean of each month, smoothed/)).toBeVisible();
  await expect(chart.getByText(/only Feb, Mar/)).toBeVisible();
  expect(jobs.length).toBe(extracted); // nothing extracted again

  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What do the charts show?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => asked.at(-1)?.view?.display).toMatch(/^anomalies against/);
});

test("cards, answers and notes are pinned to the board, and Magonia is told about them", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await expect(page.getByRole("region", { name: "NDVI chart" }).locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await page.getByRole("button", { name: "Pin NDVI to the board" }).click();
  await expect(page.getByText("Pinned NDVI to the board.")).toBeVisible();

  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("When does it peak?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText(/Orchard NDVI peaks in Aug/)).toBeVisible();
  await assistant.getByRole("button", { name: "Pin to the board" }).click();

  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Board" }).click();
  // a pinned card is the live card, not a picture of it
  const ndvi = page.getByRole("region", { name: "NDVI chart" });
  await expect(ndvi.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await ndvi.getByRole("button", { name: "Where this comes from" }).click();
  await expect(ndvi.getByText("7fd36665e815857e")).toBeVisible();
  await expect(page.getByRole("region", { name: "Magon: When does it peak?" })).toContainText("Orchard NDVI peaks in Aug");

  await page.getByRole("button", { name: "Add a note" }).click();
  await page.getByRole("textbox", { name: "Note", exact: true }).fill("Check the 2024 dip.");
  await page.getByRole("textbox", { name: "Note", exact: true }).blur();
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What did I note?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => (asked.at(-1)?.view as { board?: { text: string }[] } | undefined)?.board?.at(-1)?.text).toBe("Check the 2024 dip.");

  await page.waitForTimeout(700);
  await page.reload();
  await expect(page.getByRole("region", { name: "NDVI chart" }).locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await page.getByRole("button", { name: "Unpin NDVI" }).click();
  await expect(page.getByRole("region", { name: "NDVI chart" })).toHaveCount(0);
  const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("each page has its own address, and back and reload keep it", async ({ page }) => {
  await expect(page).toHaveURL(/\/workspaces\/1\/map(\?|$)/);
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await expect(page).toHaveURL(/\/workspaces\/1\/data(\?|$)/);
  await expect(page.getByRole("heading", { name: "Data" })).toBeVisible();
  await expect(page.locator(".map")).toBeHidden();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("heading", { name: "Analyses" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/data(\?|$)/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Data" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" })).toHaveAttribute("aria-current", "page");
});

test("the period chosen in the month fields is the one extracted", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByLabel("From", { exact: true }).fill("2021-03");
  await expect.poll(() => (jobs.at(-1) as { start?: string } | undefined)?.start).toBe("2021-03-01");
  await expect(page.getByText("Type a month as YYYY-MM")).toHaveCount(0);
});

test("the charts show the areas together or one at a time, and keep the choice", async ({ page }) => {
  const forest = { ...SQUARE.features[0], properties: { name: "Forest" } };
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify({ ...SQUARE, features: [...SQUARE.features, forest] })),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  const chart = page.getByRole("region", { name: "NDVI chart" });
  const choice = page.getByRole("group", { name: "Areas in the charts" });
  await expect(chart.locator('.plot-svg [data-mark="line"]')).toHaveCount(2);

  await choice.getByRole("button", { name: "Forest" }).click();
  await expect(chart.locator('.plot-svg [data-mark="line"]')).toHaveCount(1);
  await expect(chart.getByRole("rowheader", { name: "Orchard" })).toHaveCount(0);

  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Map" }).click();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await expect(choice.getByRole("button", { name: "Forest" })).toHaveAttribute("aria-pressed", "true");
  await expect(chart.locator('.plot-svg [data-mark="line"]')).toHaveCount(1);

  await choice.getByRole("button", { name: "All areas" }).click();
  await expect(chart.locator('.plot-svg [data-mark="line"]')).toHaveCount(2);
});


test("SPEI can be extracted at a different time scale for one area", async ({ page }) => {
  const spei = { key: "spei", name: "SPEI", units: "", product: "SPEIbase", resolution: "0.5°", cadence: "monthly", scales: [3, 12] };
  await page.route("**/api/catalogue", (route) => route.fulfill({ json: [...CATALOGUE, spei] }));
  await page.reload();
  await expect(page.locator(".map[data-ready=true]")).toBeVisible();
  const forest = { ...SQUARE.features[0], properties: { name: "Forest" } };
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify({ ...SQUARE, features: [...SQUARE.features, forest] })),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /SPEI/ }).check();
  await expect(page.getByRole("region", { name: "SPEI-12 chart" })).toBeVisible();

  await page.getByText("A different scale for an area").click();
  await page.locator(".per-area").getByLabel("Orchard").selectOption("3");
  const chart = page.getByRole("region", { name: "SPEI chart" });
  await expect(chart.locator(".legend").getByRole("button", { name: "Orchard · SPEI-3" })).toBeVisible();
  await expect(chart.locator(".legend").getByRole("button", { name: "Forest · SPEI-12" })).toBeVisible();
  const spe = () => (jobs as unknown as { variable: string; scale: number | null }[]).filter((j) => j.variable === "spei");
  await expect.poll(() => spe().some((j) => j.scale === 3)).toBe(true);

  // the same scale as the one for all areas is not kept as the area's own
  await page.locator(".per-area").getByLabel("Orchard").selectOption("12");
  await expect(page.getByRole("region", { name: "SPEI-12 chart" })).toBeVisible();
});


test("areas and data choices survive a change of page", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  await expect(page.getByRole("region", { name: "LST chart" })).toBeVisible();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Map" }).click();
  await expect(page.locator(".map")).toBeVisible();
  await expect(page.getByRole("toolbar").getByRole("button", { name: /^Orchard/ })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Data" })).toHaveCount(0); // data choices live on the Data page
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await expect(page.getByRole("checkbox", { name: /LST/ })).toBeChecked();
});

test("Magonia opens beside a page, and the conversation carries over to its own page", async ({ page }) => {
  const assistant = page.getByRole("region", { name: "Magon" });
  await expect(assistant).toBeHidden();
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  await expect(assistant).toBeVisible();
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Magon" })).toHaveCount(0);
  await assistant.getByRole("button", { name: "Make Magon bigger" }).click();
  await expect(page).toHaveURL(/\/assistant(\?|$)/);
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByRole("button", { name: "Make Magon smaller" }).click();
  await expect(page).toHaveURL(/\/map(\?|$)/);
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByRole("button", { name: "Close Magon" }).click();
  await expect(assistant).toBeHidden();
});

test("Magon is asked about one card from the card itself, and opens from the rail or ⌘J", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await expect(assistant).toBeHidden();
  await page.getByRole("button", { name: "Ask Magon about NDVI" }).click();
  await expect(assistant).toBeVisible();
  await expect(assistant.getByRole("group", { name: "Asking about" })).toContainText("NDVI chart");
  await expect(assistant.getByRole("textbox", { name: "Ask Magon" })).toBeFocused();
  await page.keyboard.type("Was 2024 unusual?");
  await page.keyboard.press("Enter");
  await expect.poll(() => (asked.at(-1)?.view as { focus?: string } | undefined)?.focus).toBe("NDVI chart");
  // asked once: the next question is about everything open again
  await expect(assistant.getByRole("group", { name: "Asking about" })).toHaveCount(0);

  await page.locator("body").press("ControlOrMeta+j");
  await expect(assistant).toBeHidden();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("button", { name: "Magon" }).click();
  await expect(assistant).toBeVisible();
});

test("an instruction asked for in the chat is saved only on a click, and can be undone", async ({ page }) => {
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("From now on, answer in French");
  await assistant.getByRole("button", { name: "Send" }).click();
  const proposal = assistant.getByRole("group", { name: "Proposed: Answer in French." });
  await expect(proposal).toContainText("Keep as an instruction?");
  expect(instructions).toBe(""); // nothing is saved by Magon itself
  await proposal.getByRole("button", { name: "Save" }).click();
  await expect(proposal).toContainText("Saved");
  await expect.poll(() => instructions).toBe("- Answer in French.");
  await page.getByRole("status").filter({ hasText: "Saved as an instruction" }).getByRole("button", { name: "Undo" }).click();
  await expect.poll(() => instructions).toBe("");
});

test("Magonia is sent what is open and says which cards it read", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("When does it peak?");
  await assistant.getByRole("button", { name: "Send" }).click();

  await expect(assistant.locator(".num.verified").first()).toHaveAttribute("title", "From NDVI chart");
  await expect(assistant.locator("mark.num.flagged")).toHaveText("0.95 (not found in what Magon was given)");
  await expect(assistant.getByText("2 of 3 numbers checked against what Magon was given")).toBeVisible();
  await expect(assistant.getByText("1 number was not confirmed: 0.95 (not found in what Magon was given).")).toBeVisible();
  const results = await new AxeBuilder({ page }).include(".assistant").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  await assistant.getByText("Based on 1 item from your workspace and 1 closer reading").click();
  await expect(assistant.locator(".used-list")).toContainText("NDVI chart");
  await expect(assistant.locator(".used-list")).toContainText("Orchard NDVI 2024");
  const { view } = asked.at(-1)!;
  expect(view?.page).toBe("data");
  expect(view?.charts).toEqual(["ndvi"]);
  expect(view?.series.map((s) => [s.area_id, s.variable])).toEqual([[1, "ndvi"]]);
});

const PROPOSING = [
  {
    type: "proposal",
    proposal: {
      kind: "trend",
      label: "Long-term trend",
      title: "Long-term trend: LST, period 2010-01 to 2020-12",
      why: "Whether the area has warmed.",
      variable: "lst",
      period: { start: "2010-01", end: "2020-12" },
    },
  },
  {
    type: "proposal",
    proposal: {
      kind: "experiment",
      label: "Forecast experiment",
      title: "Forecast experiment: NDVI with LST, Orchard",
      why: "",
      variable: "ndvi",
      drivers: ["lst"],
      area: "Orchard",
      models: ["Ridge"],
      test_years: 2,
    },
  },
  { type: "text", text: "I proposed two analyses; add them to see them." },
  { type: "check", text: "I proposed two analyses; add them to see them.", cited: [], removed: [], unverified: [] },
];

test("Magon proposes analyses, and nothing is added until the researcher clicks", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("Propose a trend of LST from 2010 to 2020 and a forecast");
  await assistant.getByRole("button", { name: "Send" }).click();
  const trend = assistant.getByRole("group", { name: /Proposed: Long-term trend/ });
  await expect(trend).toContainText("Whether the area has warmed.");
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("region", { name: "Suggested analyses" })).toBeVisible(); // nothing added yet

  await trend.getByRole("button", { name: "Add it" }).click();
  await expect(page.getByRole("region", { name: "Trend chart" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Variable" })).toHaveValue("lst");
  await expect(page.getByText(/^Data: Jan 2010 to Dec 2020/)).toBeVisible();
  await expect(trend).toContainText("Added");

  await assistant.getByRole("group", { name: /Proposed: Forecast experiment/ }).getByRole("button", { name: "Add it" }).click();
  await expect(page).toHaveURL(/\/model(\?|$)/);
  await expect.poll(() => modelled.at(-1)).toMatchObject({ models: ["Ridge"], test_years: 2 });
});

test("an answer shows its checked sources and what the check removed", async ({ page }) => {
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magon" });
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();

  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await expect(assistant.locator(".turn.assistant a.cite")).toHaveText(["1p. 6"]);
  await expect(assistant.getByRole("link", { name: "Drought stress in arid olive groves" })).toHaveAttribute(
    "href",
    "https://doi.org/10.1/1",
  );
  // the passage Magonia read, at its page, and how much of each paper it could read
  await expect(assistant.getByText("1 paper read in full")).toBeVisible();
  await expect(assistant.getByText("Read in full", { exact: false }).first()).toBeVisible();
  await assistant.getByText("Passages Magon read (p. 6)").click();
  await expect(assistant.locator(".paper .passage").first()).toContainText(
    "Rainfed groves lost NDVI within one season of drought.",
  );
  await expect(assistant.getByText("Also found, not cited (1)")).toBeVisible();
  await assistant.getByText("Also found, not cited (1)").click();
  await expect(assistant.getByText(/publisher does not allow downloads/)).toBeVisible();
  await expect(assistant.getByText("Removed a citation ([7]) that matched no paper found.")).toBeVisible();
  // the fact check: what is not supported is shown, with the passage it was checked against
  await expect(assistant.getByText("Fact check: 1 of 2 statements are supported by the papers they cite")).toBeVisible();
  await expect(assistant.locator(".statement.unsupported")).toContainText("Irrigation stops the decline entirely.");
  await expect(assistant.locator(".statement.unsupported")).toContainText("Checked against [1, p. 6]");

  const results = await new AxeBuilder({ page }).include(".assistant").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});

for (const theme of ["light", "dark"]) {
  test(`no serious accessibility problems in the ${theme} theme`, async ({ page }) => {
    if (theme === "dark") {
      await page.getByRole("button", { name: "Settings" }).click();
      await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Appearance" }).click();
      await page.getByRole("group", { name: "Theme" }).getByRole("button", { name: "Dark" }).click();
      await page.getByRole("button", { name: "Close settings" }).click();
    }
    await page.getByTestId("upload").setInputFiles({
      name: "fields.geojson",
      mimeType: "application/geo+json",
      buffer: Buffer.from(JSON.stringify(SQUARE)),
    });
    await page.getByRole("button", { name: "Magon", exact: true }).click();
    for (const name of ["Data", "Analyses", "Map"]) {
      await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name }).click();
      if (name === "Data") await expect(page.locator('.plot-svg [data-mark="line"]')).toBeVisible();
      if (name === "Analyses") {
        await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Correlation and lag/ }).click();
        await expect(page.locator('.plot-svg [data-mark="line"]').first()).toBeVisible();
      }
      const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
      const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
      expect(serious.map((v) => `${name}: ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    }
    await page.getByRole("region", { name: "Magon" }).getByRole("button", { name: "Make Magon bigger" }).click();
    const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}

test("a pinned answer keeps its citations and paper links on the board", async ({ page }) => {
  const assistant = page.getByRole("region", { name: "Magon" });
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByRole("button", { name: "Pin to the board" }).click();

  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Board" }).click();
  const pinned = page.getByRole("region", { name: "Magon: What does drought do to olive NDVI?" });
  await expect(pinned.locator(".cite", { hasText: "1" }).first()).toHaveAttribute("title", /Sghaier et al., 2022/);
  await expect(pinned.getByRole("link", { name: "Drought stress in arid olive groves" })).toHaveAttribute(
    "href",
    "https://doi.org/10.1/1",
  );
  await expect(pinned.getByText("Removed a citation ([7]) that matched no paper found.")).toBeVisible();
  const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("the board has sections, highlights and pinned passages, and Magonia is told about them", async ({ page }) => {
  const assistant = page.getByRole("region", { name: "Magon" });
  await page.getByRole("button", { name: "Magon", exact: true }).click();
  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByText("Passages Magon read (p. 6)").click();
  await assistant.getByRole("button", { name: "Pin the passage from Sghaier et al., 2022, page 6, to the board" }).click();
  await assistant.getByRole("button", { name: "Pin to the board" }).click();

  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Board" }).click();
  const passage = page.getByRole("region", { name: "Sghaier et al., 2022, p. 6" });
  await expect(passage).toContainText("Rainfed groves lost NDVI within one season of drought.");
  await expect(passage.getByRole("link", { name: "Open the paper" })).toHaveAttribute("href", "https://doi.org/10.1/1");

  // a section heads the items after it
  await page.getByRole("button", { name: "Add a section" }).click();
  const title = page.getByRole("textbox", { name: "Section title" });
  await title.fill("Drought evidence");
  await title.blur();
  await page.getByRole("button", { name: "Move Drought evidence" }).focus();
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowUp");

  // select words in the passage and highlight them
  await passage.locator(".board-passage").evaluate((quote) => {
    const text = quote.firstChild!;
    const range = document.createRange();
    range.setStart(text, 0);
    range.setEnd(text, "Rainfed groves lost NDVI".length);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
  });
  await passage.getByRole("button", { name: "Highlight" }).click();
  await expect(passage.locator(".highlights mark")).toHaveText("Rainfed groves lost NDVI");
  expect(await page.evaluate(() => CSS.highlights.get("board-highlight")?.size)).toBe(1);

  await assistant.getByRole("textbox", { name: "Ask Magon" }).fill("What did I highlight?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect
    .poll(() => (asked.at(-1)?.view as { board?: { title: string; text: string }[] } | undefined)?.board)
    .toContainEqual(
      expect.objectContaining({
        title: "[Drought evidence] Passage: Sghaier et al., 2022, p. 6",
        text: 'Highlighted: "Rainfed groves lost NDVI" Rainfed groves lost NDVI within one season of drought.',
        trust: "passage",
      }),
    );

  // highlights survive a reload, and can be removed
  await page.waitForTimeout(700);
  await page.reload();
  await expect(passage.locator(".highlights mark")).toHaveText("Rainfed groves lost NDVI");
  await passage.getByRole("button", { name: 'Remove the highlight "Rainfed groves lost NDVI"' }).click();
  await expect(passage.locator(".highlights")).toHaveCount(0);
  const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("the library takes the researcher's PDFs and their instructions for Magonia", async ({ page }) => {
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Library" }).click();
  await expect(page.getByText("No papers yet.")).toBeVisible();
  await page.getByTestId("library-upload").setInputFiles({
    name: "field_survey.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4"),
  });
  await expect(page.getByRole("button", { name: "field survey", exact: true })).toBeVisible();
  await expect(page.getByText("field_survey.pdf · 12 pages")).toBeVisible();

  const box = page.getByRole("textbox", { name: "Instructions for Magon" });
  await box.fill("Answer in French.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  expect(instructions).toBe("Answer in French.");

  await page.reload();
  await expect(page.getByRole("textbox", { name: "Instructions for Magon" })).toHaveValue("Answer in French.");
  // read inside Magonia, then removed and brought back
  await page.getByRole("button", { name: "field survey", exact: true }).click();
  const reader = page.getByRole("dialog", { name: "Reading field survey" });
  await expect(reader.locator("iframe")).toHaveAttribute("src", "/api/library/U1/pdf");
  await page.keyboard.press("Escape");
  await expect(reader).toHaveCount(0);
  await page.getByRole("button", { name: "Remove field survey from the library" }).click();
  await expect(page.getByText("No papers yet.")).toBeVisible();
  await page.getByRole("status").filter({ hasText: "removed from the library" }).getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "field survey", exact: true })).toBeVisible();
  const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("the map draws a variable for a month, steps months by key, and keeps the view in its address", async ({ page }) => {
  await page.keyboard.press("l");
  const panel = page.getByRole("region", { name: "Map layers" });
  await expect(panel).toBeVisible();
  await expect.poll(() => tilesAsked.at(-1)?.variable).toBe("ndvi");
  const first = tilesAsked.at(-1)!.month;
  await page.locator("body").press("[");
  await expect.poll(() => tilesAsked.at(-1)?.month).not.toBe(first);
  await expect(panel.getByText("NDVI · ")).toBeVisible();
  await expect(page).toHaveURL(/layer=ndvi/);
  await expect(page).toHaveURL(/month=\d{4}-\d{2}/);
});

test("a pixel is inspected on its own, and can become an area", async ({ page }) => {
  await page.getByRole("button", { name: "Inspect a pixel" }).click();
  const map = (await page.locator(".map").boundingBox())!;
  await page.mouse.click(map.x + map.width / 2, map.y + map.height / 2);
  const inspector = page.getByRole("region", { name: "Pixel inspector" });
  await expect(inspector.getByText("250 m · 24 of 24 dates with a value")).toBeVisible();
  await expect(inspector.locator('.plot-svg [data-mark="line"]')).toBeVisible();
  await inspector.getByRole("button", { name: "Make this pixel an area" }).click();
  await expect(page.getByRole("toolbar", { name: "Areas" }).getByText(/Pixel 36\.\d+, 8\.\d+/)).toBeVisible();
  await page.locator("body").press("Escape");
  await expect(inspector).toBeHidden();
});

test("coordinates typed as a box become an area", async ({ page }) => {
  await page.getByRole("button", { name: "Enter coordinates" }).click();
  await page.getByRole("textbox", { name: "Coordinates" }).fill("8.55, 36.50, 8.57, 36.52");
  await expect(page.getByText("Area with 4 corners")).toBeVisible();
  await page.getByRole("button", { name: "Add area" }).click();
  await expect(page.getByRole("toolbar", { name: "Areas" }).getByText("Area 1")).toBeVisible();
});

test("⌘K finds any action by name", async ({ page }) => {
  await page.locator("body").press("ControlOrMeta+k");
  const palette = page.getByRole("dialog", { name: "Commands" });
  await page.getByRole("textbox", { name: "Command" }).fill("go data");
  await page.keyboard.press("Enter");
  await expect(palette).toBeHidden();
  await expect(page).toHaveURL(/\/data(\?|$)/);
});

test("hovering a date marks it on every chart, and a click picks the map's month", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  const charts = page.locator(".chart-box");
  await expect(charts).toHaveCount(2);
  const box = (await charts.first().boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5);
  await expect(page.locator(".chart-rule:not(.chosen)")).toHaveCount(2);
  await expect(page.locator(".chart-tip")).toHaveCount(1);
  await page.mouse.click(box.x + box.width * 0.6, box.y + box.height * 0.5);
  await expect(page.locator(".chart-rule.chosen")).toHaveCount(2);
  await expect(page).toHaveURL(/month=\d{4}-\d{2}/);
});

test("the Data page shows every observation as boxplots by month, season or all together", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("button", { name: "Distribution" }).click();
  const chart = page.getByRole("region", { name: "NDVI chart" });
  await expect(chart.locator('.plot-svg [data-mark="bar"]').first()).toBeVisible();
  await chart.getByRole("button", { name: "By season" }).click();
  await expect(chart.locator(".plot-svg")).toContainText("Winter");
  await page.getByRole("button", { name: "Seasonal cycle" }).click();
  await chart.getByRole("button", { name: "Median" }).click();
  await expect(chart.getByRole("button", { name: "Median" })).toHaveAttribute("aria-pressed", "true");
});

test("a drought-scale analysis asks for SPEI at every scale and says which one is followed", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /drought scale/ }).click();
  const card = page.getByRole("region", { name: "Drought scale chart" });
  await expect(card.locator('.plot-svg [data-mark="cell"]').first()).toBeVisible();
  await expect.poll(() => jobs.filter((j) => (j as { variable: string }).variable === "spei").map((j) => (j as { scale: number }).scale).sort((a, b) => a - b)).toEqual(
    expect.arrayContaining([1, 2, 3, 4, 6, 9, 12]),
  );
  await expect(card.getByText(/follow SPEI-\d+ from/)).toBeVisible();
});

test("a correlation can be split into its trend and seasonal parts", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Correlation and lag/ }).click();
  const card = page.getByRole("region", { name: "Correlation chart" });
  await card.getByRole("checkbox", { name: /trend and seasonal parts/ }).check();
  await expect(card.getByRole("cell", { name: "Trend", exact: true })).toBeVisible();
  await expect(card.getByRole("cell", { name: "Seasonal", exact: true })).toBeVisible();
});

test("wavelet coherence maps two variables over time and period", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /move together/ }).click();
  const card = page.getByRole("region", { name: "Coherence chart" });
  await expect(card.locator('.plot-svg [data-mark="rect"]').first()).toBeVisible();
  await expect(card.getByText(/At the annual period, NDVI and LST are coherent/)).toBeVisible();
  const results = await new AxeBuilder({ page }).include("[aria-label='Coherence chart']").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("a leakage audit sets whole-record against past-only decomposition, with a noise placebo", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /skill real/ }).click();
  const card = page.getByRole("region", { name: "Leakage audit" });
  await expect(card.getByRole("row", { name: /White noise/ })).toContainText("0.99");
  await expect(card.getByText(/On white noise, where nothing can be forecast/)).toBeVisible();
  await expect(card.locator('.plot-svg [data-mark="line"]').first()).toBeVisible();
});

test("pixel purity maps how much of each pixel around an area is annual crop", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /crop I think it is/ }).click();
  const card = page.getByRole("region", { name: "Pixel purity" });
  await expect(card.locator('.plot-svg [data-mark="geo"]').first()).toBeVisible();
  await expect(card.getByText(/40% annual crop and 60% perennial/)).toBeVisible();
  await expect(page.getByRole("button", { name: /notebook/i })).toHaveCount(0);
});
