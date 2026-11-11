import { expect, test } from "@playwright/test";
import {
  expectNoFatalUiError,
  openProject,
  pickProjectForBlockers,
} from "./helpers";

test.describe("Blocker detection", () => {
  test("renders blocker page or live-project empty state", async ({ page }) => {
    const projectKey = await pickProjectForBlockers(page);
    await openProject(page, "/blockers", projectKey);

    await expect(page.getByRole("banner").getByRole("heading", { name: /Blocker Detection/i })).toBeVisible();
    await expect(page.getByText(/Import a Trello board to detect blockers|escalation|impact|stalled|no active blockers/i).first()).toBeVisible();
    await expectNoFatalUiError(page);
  });
});
