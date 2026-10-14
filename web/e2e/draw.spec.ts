import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// A small in-memory stand-in for the Magonia API, so the tests need neither the
// API nor Earth Engine
async function fakeApi(page: Page, connected = true) {
  const areas: { id: number; workspace_id: number; name: string; geometry: unknown; area_km2: number }[] = [];
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
    route.request().method() === "PATCH" ? route.fulfill({ json: {} }) : route.fulfill({
      json: { id: 1, name: "My workspace", created: "", updated: "", settings: {}, areas, jobs: [] },
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
  const chart = page.getByRole("region", { name: "NDVI chart" });
  await expect(chart.locator(".recharts-line")).toBeVisible();
  await expect(chart.getByRole("rowheader", { name: "Orchard" })).toBeVisible();
  await chart.getByRole("button", { name: "Where this comes from" }).click();
  await expect(chart.getByText("7fd36665e815857e")).toBeVisible();
  await expect(page.getByText(/Orchard: NDVI peaks in/)).toBeVisible();
  await page.getByRole("button", { name: "Seasonal cycle" }).click();
  await expect(chart.getByText("Average year", { exact: false })).toBeVisible();
});

test("choosing a second variable shows how the two are correlated over lags", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await expect(page.getByRole("region", { name: "Correlation chart" })).toHaveCount(0);
  await page.getByRole("checkbox", { name: /LST/ }).check();
  const card = page.getByRole("region", { name: "Correlation chart" });
  await expect(card.locator(".recharts-line")).toBeVisible();
  // the fake API returns the same series for both variables, so they match in the same month
  await expect(card.getByText(/Orchard: NDVI anomalies are most closely linked to LST anomalies from the same month \(r = 1\.00\)/)).toBeVisible();
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
  await expect(page.getByRole("complementary", { name: "Results" })).toBeHidden();
  await page.getByRole("button", { name: "Show panels" }).click();
  await expect(page.getByRole("complementary", { name: "Results" })).toBeVisible();
});

for (const theme of ["light", "dark"]) {
  test(`no serious accessibility problems in the ${theme} theme`, async ({ page }) => {
    if (theme === "dark") await page.getByRole("button", { name: "Switch to dark theme" }).click();
    await page.getByTestId("upload").setInputFiles({
      name: "fields.geojson",
      mimeType: "application/geo+json",
      buffer: Buffer.from(JSON.stringify(SQUARE)),
    });
    await expect(page.locator(".recharts-line")).toBeVisible();
    const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
    const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}
