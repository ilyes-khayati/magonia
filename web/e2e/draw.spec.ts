import { expect, test } from "@playwright/test";

test("drawing an area shows its NDVI curve", async ({ page }) => {
  // Fake the API so the test does not need Earth Engine
  await page.route("**/api/series", (route) =>
    route.fulfill({
      json: {
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
      },
    }),
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
});
