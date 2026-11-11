import { test, expect } from "@playwright/test";

test.describe("Sprint Monitor", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/sprint-monitor");
  });

  test("renders sprint monitor elements", async ({ page }) => {
    await expect(page.getByRole("banner").getByRole("heading", { name: /KPIMaster|Sprint Monitor/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to monitor sprint flow|Sprint Monitor|Pulse/i).first()).toBeVisible();

    const chart = page.locator(".recharts-responsive-container").first();
    if (await chart.count()) {
      await expect(chart).toBeVisible();
    }
  });
});
