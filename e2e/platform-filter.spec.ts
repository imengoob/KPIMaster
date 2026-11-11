import { expect, test } from "@playwright/test";
import {
  authenticatePageWithToken,
  expectNoFatalUiError,
  loginViaApi,
  openProject,
  pickProjectKey,
} from "./helpers";

test.describe("Global platform filter", () => {
  test("switches Trello-only pages into the provider guard and persists the selection", async ({ page, request }) => {
    const token = await loginViaApi(request, {
      username: "horizon_admin",
      password: "ChangeMe123!",
    });
    await authenticatePageWithToken(page, token);
    const projectKey = await pickProjectKey(page);

    await openProject(page, "/dashboard", projectKey);
    await page.getByTestId("platform-filter-trigger").click();
    await page.getByRole("option", { name: "GitHub" }).click();

    await expect(page.getByText(/Switch the platform filter from GitHub to Trello or All Platforms/i)).toBeVisible();

    await openProject(page, "/repository", projectKey);
    await expect(page.getByText(/Filtered by GitHub/i)).toBeVisible();
    await expect(page.getByTestId("platform-filter-trigger")).toContainText("GitHub");
    await expectNoFatalUiError(page);
  });
});
