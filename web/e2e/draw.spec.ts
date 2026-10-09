import { expect, test } from "@playwright/test";

test("drawing an area shows its NDVI curve", async ({ page }) => {
  // Fake the API so the test does not need Earth Engine
  await page.route("**/api/series", (route) =>
    route.fulfill({
      json: [
        { date: "2023-01-01", ndvi: 0.58 },
        { date: "2023-01-17", ndvi: 0.6 },
        { date: "2023-02-02", ndvi: 0.55 },
      ],
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Draw an area" }).click();

  const map = page.locator(".map");
  for (const [x, y] of [[500, 300], [700, 300], [700, 450], [500, 450], [500, 300]]) {
    await map.click({ position: { x, y } });
  }

  await expect(page.locator(".recharts-line")).toBeVisible();
});
