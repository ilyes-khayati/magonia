import { expect, test, type Page } from "@playwright/test";

// A small in-memory stand-in for the Magonia API, so the tests need neither the
// API nor Earth Engine
async function fakeApi(page: Page) {
  const areas: { id: number; workspace_id: number; name: string; geometry: unknown; area_km2: number }[] = [];
  await page.route("**/api/catalogue", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/workspaces", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, json: { id: 1, name: "My workspace", created: "", updated: "" } })
      : route.fulfill({ json: [] }),
  );
  await page.route("**/api/workspaces/1", (route) =>
    route.fulfill({
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

test.beforeEach(async ({ page }) => {
  await fakeApi(page);
  await page.goto("/");
  await expect(page.locator(".map[data-ready=true]")).toBeVisible();
});

test("drawing a polygon saves it as an area", async ({ page }) => {
  await page.getByRole("button", { name: "Draw a polygon" }).click();
  const map = page.locator(".map");
  for (const [x, y] of [[300, 300], [450, 300], [450, 420], [300, 420], [300, 300]]) {
    await map.click({ position: { x, y } });
  }
  await expect(page.getByRole("button", { name: /^Area 1/ })).toBeVisible();
});

test("uploading a GeoJSON file adds its named areas", async ({ page }) => {
  await page.getByTestId("upload").setInputFiles({
    name: "fields.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(SQUARE)),
  });
  await expect(page.getByRole("button", { name: /^Orchard/ })).toBeVisible();
  await expect(page.getByText("Added 1 area from fields.geojson.")).toBeVisible();
});

test("the theme can be switched to dark", async ({ page }) => {
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
