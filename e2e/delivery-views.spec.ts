import { expect, test } from "@playwright/test";
import {
  expectNoFatalUiError,
  openProject,
  pickProjectForClientProgress,
  pickProjectForRepository,
} from "./helpers";

test.describe("Developer, client, and repository delivery views", () => {
  test("renders developer progress or live-project empty state", async ({ page }) => {
    const projectKey = await pickProjectForClientProgress(page);
    await openProject(page, "/developers", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /Developer Progress/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to track developer KPIs|Developer KPI Dashboard|Manager Alerts|On Track|At Risk|Behind/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });

  test("renders the client progress dashboard or live-project empty state", async ({ page }) => {
    const projectKey = await pickProjectForClientProgress(page);
    await openProject(page, "/client-progress", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /Client Progress/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to open the client delivery dashboard|Client Delivery View|Developer delivery status|Delivery note/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });

  test("renders repository view or live-project empty state", async ({ page }) => {
    const projectKey = await pickProjectForRepository(page);
    await openProject(page, "/repository", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /Repository/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to inspect repository mismatches|Repository Integration|Stalled Tickets Detected|No repository activity found/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });
});
