import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// A small in-memory stand-in for the Magonia API, so the tests need neither the
// API nor Earth Engine
// What the interface sent with each question, for tests to inspect
let asked: {
  content: string;
  view?: { page: string; charts: string[]; series: { area_id: number; variable: string }[]; display?: string | null };
}[] = [];

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
let lagged: { response: { variable: string }; drivers: { variable: string }[]; deseasonalise: boolean }[] = [];

async function fakeApi(page: Page, connected = true) {
  asked = [];
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
  await page.route("**/api/workspaces", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: { id: 1, name: "My workspace", created: "", updated: "" } })
      : route.fulfill({ json: [] }),
  );
  await page.route("**/api/workspaces/1", (route) =>
    route.request().method() === "PATCH"
      ? ((settings = route.request().postDataJSON().settings ?? settings), route.fulfill({ json: {} }))
      : route.fulfill({
          json: { id: 1, name: "My workspace", created: "", updated: "", settings, areas, jobs: [] },
        }),
  );
  await page.route("**/api/assistant", (route) => route.fulfill({ json: { name: "Magonia", model: "test model" } }));
  await page.route("**/api/workspaces/1/messages", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/workspaces/1/chat", (route) => {
    asked.push(route.request().postDataJSON());
    const question = asked.at(-1)!.content;
    const answer = question.startsWith("Propose") ? PROPOSING : asked.at(-1)!.view?.series.length ? DATA_ANSWER : ANSWER;
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
  { type: "text", text: "Drought lowers olive NDVI [1], as also shown in [7]." },
  { type: "check", text: "Drought lowers olive NDVI [1], as also shown in.", cited: [1], removed: [7], unverified: [] },
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

test("the theme can be switched to dark", async ({ page }) => {
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
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
  await expect(chart.locator(".recharts-line")).toBeVisible();
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
  await expect(card.locator(".recharts-line")).toBeVisible();
  // the fake API returns the same series for both variables, so they match in the same month
  await expect(card.getByText(/Orchard: NDVI anomalies are most closely linked to LST anomalies from the same month \(r = 1\.00\)/)).toBeVisible();

  await card.getByRole("checkbox", { name: "Remove seasonal cycle" }).uncheck();
  await expect(card.getByRole("list", { name: "Cautions" })).toContainText("months in common"); // a guardrail
  await page.waitForTimeout(700); // saving waits half a second after the last change
  await page.reload();
  await expect(card.locator(".recharts-line")).toBeVisible();
  await expect(card.getByRole("checkbox", { name: "Remove seasonal cycle" })).not.toBeChecked();

  await card.getByRole("button", { name: "Remove this analysis" }).click();
  await expect(page.getByRole("region", { name: "Suggested analyses" })).toBeVisible();
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
  await expect(card.locator(".recharts-line")).toBeVisible();
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
  await expect(card.locator(".recharts-line")).toHaveCount(3); // value and trend above, season below
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
  await expect(card.getByRole("list", { name: "Cautions" })).toContainText("only 4 complete years");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Long-term trend as a notebook" }).click();
  expect((await download).suggestedFilename()).toBe("long-term-trend.ipynb");
  expect(exported.at(-1)).toMatchObject({ kind: "trend", series: [{ variable: "ndvi" }] });
  const results = await new AxeBuilder({ page }).include("[aria-label='Trend chart']").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
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
  await expect(card.locator(".recharts-bar-rectangle")).toHaveCount(24);
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
  await page.getByRole("region", { name: "Suggested experiments" }).getByRole("button", { name: /The paper's method/ }).click();

  const experiment = page.getByRole("region", { name: "Experiment" });
  await expect(experiment.getByRole("combobox", { name: "Start from" })).toHaveValue("paper");
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
  expect(modelled.at(-1)).not.toHaveProperty("models"); // the paper's request, unchanged

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

  // a copy with one change, then the two side by side
  await experiment.getByRole("button", { name: "Duplicate" }).click();
  await experiment.getByRole("checkbox", { name: "Ridge" }).uncheck();
  await experiment.getByRole("group", { name: "XGBoost settings" }).getByRole("button", { name: "Set by hand" }).click();
  await experiment.getByRole("spinbutton", { name: "Maximum depth" }).first().fill("3");
  await experiment.getByRole("spinbutton", { name: "Maximum depth" }).first().blur();
  await experiment.getByRole("checkbox", { name: /Calendar month/ }).uncheck();
  await expect(experiment.getByRole("combobox", { name: "Start from" })).toHaveValue("custom");
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
  await expect(page.getByText("Earth Engine · my-project")).toBeVisible();
});

test("focus mode hides the top bar", async ({ page }) => {
  await page.getByRole("button", { name: "Focus map" }).click();
  await expect(page.getByRole("banner")).toBeHidden();
  await page.getByRole("button", { name: "Show panels" }).click();
  await expect(page.getByRole("banner")).toBeVisible();
});

test("the workspace is named in the top bar and can be renamed", async ({ page }) => {
  const renamed: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "PATCH" && r.url().endsWith("/workspaces/1") && r.postDataJSON().name) renamed.push(r.postDataJSON().name);
  });
  const menu = page.getByRole("banner").getByRole("button", { name: /My workspace/ });
  await menu.click();
  await page.getByRole("group", { name: "Workspaces" }).getByRole("button", { name: "Rename this workspace…" }).click();
  await page.getByRole("textbox", { name: "Name" }).fill("Jendouba orchard");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(page.getByRole("banner").getByRole("button", { name: /Jendouba orchard/ })).toBeVisible();
  expect(renamed).toEqual(["Jendouba orchard"]);
});

test("Magonia's panel can be widened by its edge, and stays open across pages", async ({ page }) => {
  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Magonia" });
  const before = (await panel.boundingBox())!.width;
  const edge = page.getByRole("separator", { name: "Resize Magonia" });
  await edge.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await panel.boundingBox())!.width).toBe(before + 80);
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("region", { name: "Magonia assistant" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Magonia assistant" })).toBeVisible();
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
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect(titles).toHaveText(["NDVI", "LST"]);

  await page.getByRole("button", { name: "Full width: NDVI" }).click();
  const ndvi = page.getByRole("region", { name: "NDVI chart" });
  const lst = page.getByRole("region", { name: "LST chart" });
  await expect(page.locator(".slot", { has: ndvi })).toHaveAttribute("data-wide", "true"); // spans every column
  await page.getByRole("button", { name: "Show LST" }).click();
  await expect(lst.locator(".recharts-wrapper")).toBeHidden();
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
  await expect(chart.locator(".recharts-line")).toBeVisible();
  const extracted = jobs.length;
  const panel = page.getByRole("complementary", { name: "Data" });
  await panel.getByRole("checkbox", { name: "Smooth" }).check();
  await panel.getByRole("checkbox", { name: "Anomalies" }).check();
  await panel.getByRole("button", { name: "January" }).click();
  await expect(chart.getByText(/anomalies against the 2020–2024 mean of each month, smoothed/)).toBeVisible();
  await expect(chart.getByText(/only Feb, Mar/)).toBeVisible();
  expect(jobs.length).toBe(extracted); // nothing extracted again

  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("What do the charts show?");
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
  await expect(page.getByRole("region", { name: "NDVI chart" }).locator(".recharts-line")).toBeVisible();
  await page.getByRole("button", { name: "Pin NDVI to the board" }).click();
  await expect(page.getByText("Pinned NDVI to the board.")).toBeVisible();

  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("When does it peak?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText(/Orchard NDVI peaks in Aug/)).toBeVisible();
  await assistant.getByRole("button", { name: "Pin to the board" }).click();

  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Board" }).click();
  const ndvi = page.getByRole("region", { name: "NDVI", exact: true });
  await expect(ndvi.getByRole("img", { name: "NDVI, as pinned" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Magonia: When does it peak?" })).toContainText("Orchard NDVI peaks in Aug");

  await page.getByRole("button", { name: "Add a note" }).click();
  await page.getByRole("textbox", { name: "Note", exact: true }).fill("Check the 2024 dip.");
  await page.getByRole("textbox", { name: "Note", exact: true }).blur();
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("What did I note?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => (asked.at(-1)?.view as { board?: { text: string }[] } | undefined)?.board?.at(-1)?.text).toBe("Check the 2024 dip.");

  await page.waitForTimeout(700);
  await page.reload();
  await expect(page.getByRole("region", { name: "NDVI", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remove NDVI from the board" }).click();
  await expect(page.getByRole("region", { name: "NDVI", exact: true })).toHaveCount(0);
  const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
  expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
});

test("each page has its own address, and back and reload keep it", async ({ page }) => {
  await expect(page).toHaveURL(/\/workspaces\/1\/map$/);
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await expect(page).toHaveURL(/\/workspaces\/1\/data$/);
  await expect(page.getByRole("heading", { name: "Data" })).toBeVisible();
  await expect(page.locator(".map")).toBeHidden();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("heading", { name: "Analyses" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/data$/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Data" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" })).toHaveAttribute("aria-current", "page");
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
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await expect(assistant).toBeHidden();
  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  await expect(assistant).toBeVisible();
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Magonia" })).toHaveCount(0);
  await assistant.getByRole("button", { name: "Make Magonia bigger" }).click();
  await expect(page).toHaveURL(/\/assistant$/);
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByRole("button", { name: "Make Magonia smaller" }).click();
  await expect(page).toHaveURL(/\/map$/);
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByRole("button", { name: "Close Magonia" }).click();
  await expect(assistant).toBeHidden();
});

test("Magonia is sent what is open and says which cards it read", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Data" }).click();
  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("When does it peak?");
  await assistant.getByRole("button", { name: "Send" }).click();

  await expect(assistant.locator(".num.verified").first()).toHaveAttribute("title", "From NDVI chart");
  await expect(assistant.locator("mark.num.flagged")).toHaveText("0.95 (not found in what Magonia was given)");
  await expect(assistant.getByText("2 of 3 numbers checked against what Magonia was given")).toBeVisible();
  await expect(assistant.getByText("1 number was not confirmed: 0.95 (not found in what Magonia was given).")).toBeVisible();
  const results = await new AxeBuilder({ page }).include(".assistant").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  await expect(assistant.getByText("From your workspace: NDVI chart · looked closer at Orchard NDVI 2024")).toBeVisible();
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

test("Magonia proposes analyses, and nothing is added until the researcher clicks", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("Propose a trend of LST from 2010 to 2020 and a forecast");
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
  await expect(page).toHaveURL(/\/model$/);
  await expect.poll(() => modelled.at(-1)).toMatchObject({ models: ["Ridge"], test_years: 2 });
});

test("an answer shows its checked sources and what the check removed", async ({ page }) => {
  await page.getByRole("button", { name: "Magonia", exact: true }).click();
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();

  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await expect(assistant.locator(".turn.assistant a.cite")).toHaveText(["1"]);
  await expect(assistant.getByRole("link", { name: "Drought stress in arid olive groves" })).toHaveAttribute(
    "href",
    "https://doi.org/10.1/1",
  );
  await expect(assistant.getByText("Also found, not cited (1)")).toBeVisible();
  await expect(assistant.getByText("Removed a citation ([7]) that matched no paper found.")).toBeVisible();

  const results = await new AxeBuilder({ page }).include(".assistant").analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});

for (const theme of ["light", "dark"]) {
  test(`no serious accessibility problems in the ${theme} theme`, async ({ page }) => {
    if (theme === "dark") await page.getByRole("button", { name: "Switch to dark theme" }).click();
    await page.getByTestId("upload").setInputFiles({
      name: "fields.geojson",
      mimeType: "application/geo+json",
      buffer: Buffer.from(JSON.stringify(SQUARE)),
    });
    await page.getByRole("button", { name: "Magonia", exact: true }).click();
    for (const name of ["Data", "Analyses", "Map"]) {
      await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name }).click();
      if (name === "Data") await expect(page.locator(".recharts-line")).toBeVisible();
      if (name === "Analyses") {
        await page.getByRole("region", { name: "Suggested analyses" }).getByRole("button", { name: /Correlation and lag/ }).click();
        await expect(page.locator(".recharts-line").first()).toBeVisible();
      }
      const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
      const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
      expect(serious.map((v) => `${name}: ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    }
    await page.getByRole("region", { name: "Magonia assistant" }).getByRole("button", { name: "Make Magonia bigger" }).click();
    const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}
