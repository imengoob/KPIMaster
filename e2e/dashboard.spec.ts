import { expect, test } from "@playwright/test";
import {
  expectNoFatalUiError,
  openProject,
  pickProjectKey,
} from "./helpers";

test.describe("Dashboard and project selection", () => {
  test("loads the dashboard shell and live-project empty state", async ({ page }) => {
    const projectKey = await pickProjectKey(page);
    await openProject(page, "/dashboard", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /^Dashboard$/i })).toBeVisible();
    await expect(page.getByText(/Connect a Trello board to get started|velocity/i).first()).toBeVisible();
    await expect(page.getByText(/Import a Trello board in Integrations|completion/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });

  test("shows the empty project switcher state in a fresh workspace", async ({ page }) => {
    await openProject(page, "/dashboard");

    await expect(page.getByTestId("project-switcher-trigger")).toContainText(/No live project connected/i);
    await page.getByTestId("project-switcher-trigger").click();
    await expect(page.getByText(/Import a Trello board in Integrations/i)).toBeVisible();
    await expectNoFatalUiError(page);
  });
});
