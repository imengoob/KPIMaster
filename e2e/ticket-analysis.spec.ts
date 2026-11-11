import { expect, test } from "@playwright/test";
import { expectNoFatalUiError, openProject, pickProjectKey } from "./helpers";

test.describe("Sprint and ticket analysis flows", () => {
  test("opens sprint monitor for a real project", async ({ page }) => {
    const projectKey = await pickProjectKey(page);
    await openProject(page, "/sprint", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /KPIMaster|Sprint Monitor/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to monitor sprint flow|Sprint Health|Story Points|Done Tickets|Blocked/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });

  test("opens ticket analysis and renders real ticket content", async ({ page }) => {
    const projectKey = await pickProjectKey(page);
    await openProject(page, "/tickets", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /Ticket Analysis/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to analyze tickets|Average Quality|Needs Attention|High Quality/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });
});
