import { expect, test } from "@playwright/test";

const CATALOGUE = [
  { key: "ndvi", name: "NDVI", units: "", scales: [] },
  { key: "lst", name: "Land surface temperature (day)", units: "°C", scales: [] },
  { key: "spei", name: "SPEI", units: "", scales: [1, 3, 6, 12, 24, 48] },
];

const RESULT = {
  variable: "ndvi",
  name: "NDVI",
  units: "",
  points: [
    { date: "2023-01-01", value: 0.58, sd: 0.05, n_pixels: 18, masked: false },
    { date: "2023-01-17", value: null, sd: null, n_pixels: 0, masked: true },
    { date: "2023-02-02", value: 0.55, sd: 0.04, n_pixels: 18, masked: false },
    { date: "2023-02-18", value: 0.6, sd: 0.05, n_pixels: 18, masked: false },
  ],
  warnings: ["This area is smaller than one pixel."],
};

test("drawing an area shows its NDVI curve", async ({ page }) => {
  await page.route("**/api/catalogue", (route) => route.fulfill({ json: CATALOGUE }));
  // Fake the API so the test does not need Earth Engine: the job is queued, then done
  await page.route("**/api/jobs", (route) =>
    route.fulfill({ json: { id: 1, status: "queued", error: null, result: null } }),
  );
  await page.route("**/api/jobs/1", (route) =>
    route.fulfill({ json: { id: 1, status: "done", error: null, result: RESULT } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Draw an area" }).click();

  const map = page.locator(".map");
  for (const [x, y] of [[500, 300], [700, 300], [700, 450], [500, 450], [500, 300]]) {
    await map.click({ position: { x, y } });
  }

  await expect(page.locator(".recharts-line")).toBeVisible();
  await expect(page.getByText("1 date without usable data")).toBeVisible();
  await expect(page.getByText("smaller than one pixel")).toBeVisible();
  await expect(page.getByLabel("Variable").locator("option")).toHaveText(
    CATALOGUE.map((variable) => variable.name),
  );
});
