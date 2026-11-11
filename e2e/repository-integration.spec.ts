import { test, expect } from "@playwright/test";

test.describe("Repository Integration", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/repository-integration");
  });

  test("renders repository integration dashboard elements", async ({ page }) => {
    await expect(page.getByRole("banner").getByRole("heading", { name: /KPIMaster|Repository/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to inspect repository mismatches|Repository Integration|Repository Mismatches/i).first()).toBeVisible();

    const scanButton = page.getByRole("button", { name: /Trigger Scan|Scan Repo|Refresh/i });
    await expect(scanButton).toBeVisible();
  });
});
