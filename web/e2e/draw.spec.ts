import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// A small in-memory stand-in for the Magonia API, so the tests need neither the
// API nor Earth Engine
async function fakeApi(page: Page, connected = true) {
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
  await page.route("**/api/jobs", (route) =>
    route.fulfill({ status: 202, json: { id: 1, status: "done", error: null, result: RESULT } }),
  );
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
  await page.route("**/api/workspaces/1/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body: ANSWER.map((event) => JSON.stringify(event)).join("\n") + "\n",
    }),
  );
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
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Charts" }).click();
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
  await page.getByRole("checkbox", { name: /LST/ }).check();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByText("No analyses yet.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Correlation chart" })).toHaveCount(0);

  await page.getByRole("button", { name: "Add analysis" }).click();
  await page.getByRole("group", { name: "Analysis types" }).getByRole("button", { name: /Correlation and lag/ }).click();
  const card = page.getByRole("region", { name: "Correlation chart" });
  await expect(card.locator(".recharts-line")).toBeVisible();
  // the fake API returns the same series for both variables, so they match in the same month
  await expect(card.getByText(/Orchard: NDVI anomalies are most closely linked to LST anomalies from the same month \(r = 1\.00\)/)).toBeVisible();

  await card.getByRole("checkbox", { name: "Remove seasonal cycle" }).uncheck();
  await page.waitForTimeout(700); // saving waits half a second after the last change
  await page.reload();
  await expect(card.locator(".recharts-line")).toBeVisible();
  await expect(card.getByRole("checkbox", { name: "Remove seasonal cycle" })).not.toBeChecked();

  await card.getByRole("button", { name: "Remove this analysis" }).click();
  await expect(page.getByText("No analyses yet.")).toBeVisible();
});

test("an analysis fetches its variables even when they are not charted", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await page.getByRole("button", { name: "Add analysis" }).click();
  await page.getByRole("button", { name: /Correlation and lag/ }).click();
  const card = page.getByRole("region", { name: "Correlation chart" });
  await expect(card.getByRole("combobox", { name: "Driver" })).toHaveValue("lst");
  await expect(card.locator(".recharts-line")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /LST/ })).not.toBeChecked();
});

test("when Earth Engine is not connected, the setup explains how and saves the project", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "Connect Google Earth Engine" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Project id").fill("my-project");
  await dialog.getByRole("button", { name: "Connect" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Earth Engine · my-project")).toBeVisible();
});

test("focus mode hides the panels", async ({ page }) => {
  await page.getByRole("button", { name: "Focus map" }).click();
  await expect(page.getByRole("complementary", { name: "Data" })).toBeHidden();
  await page.getByRole("button", { name: "Show panels" }).click();
  await expect(page.getByRole("complementary", { name: "Data" })).toBeVisible();
});

test("each page has its own address, and back and reload keep it", async ({ page }) => {
  await expect(page).toHaveURL(/\/workspaces\/1\/map$/);
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Charts" }).click();
  await expect(page).toHaveURL(/\/workspaces\/1\/charts$/);
  await expect(page.getByRole("heading", { name: "Charts" })).toBeVisible();
  await expect(page.locator(".map")).toBeHidden();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Analyses" }).click();
  await expect(page.getByRole("heading", { name: "Analyses" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/charts$/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Charts" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Charts" })).toHaveAttribute("aria-current", "page");
});

test("areas and data choices survive a change of page", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Charts" }).click();
  await page.getByRole("checkbox", { name: /LST/ }).check();
  await expect(page.getByRole("region", { name: "LST chart" })).toBeVisible();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Map" }).click();
  await expect(page.locator(".map")).toBeVisible();
  await expect(page.getByRole("toolbar").getByRole("button", { name: /^Orchard/ })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /LST/ })).toBeChecked();
});

test("Magonia opens beside a page, and the conversation carries over to its own page", async ({ page }) => {
  const assistant = page.getByRole("region", { name: "Magonia assistant" });
  await expect(assistant).toBeHidden();
  await page.getByRole("button", { name: "Beside" }).click();
  await expect(assistant).toBeVisible();
  await assistant.getByRole("textbox", { name: "Ask Magonia" }).fill("What does drought do to olive NDVI?");
  await assistant.getByRole("button", { name: "Send" }).click();
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await assistant.getByRole("button", { name: "Open Magonia on its own page" }).click();
  await expect(page).toHaveURL(/\/assistant$/);
  await expect(assistant.getByText("Drought lowers olive NDVI")).toBeVisible();
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Map" }).click();
  await assistant.getByRole("button", { name: "Close Magonia" }).click();
  await expect(assistant).toBeHidden();
});

test("an answer shows its checked sources and what the check removed", async ({ page }) => {
  await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Magonia" }).click();
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
    await page.getByRole("button", { name: "Beside" }).click();
    for (const name of ["Charts", "Analyses", "Map"]) {
      await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name }).click();
      if (name === "Charts") await expect(page.locator(".recharts-line")).toBeVisible();
      if (name === "Analyses") {
        await page.getByRole("button", { name: "Add analysis" }).click();
        await page.getByRole("button", { name: /Correlation and lag/ }).click();
        await expect(page.locator(".recharts-line").first()).toBeVisible();
      }
      const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
      const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
      expect(serious.map((v) => `${name}: ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    }
    await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Magonia" }).click();
    const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}
