import fs from "node:fs";
import { expect, test } from "@playwright/test";
import { AUTH_CREDENTIALS_FILE, loginViaUi } from "./helpers";

test.describe("Authentication", () => {
  test("can sign out and sign back in with the created account", async ({ page }) => {
    const credentials = JSON.parse(
      fs.readFileSync(AUTH_CREDENTIALS_FILE, "utf-8"),
    ) as { username: string; password: string };

    await page.goto("/dashboard");
    const signOut = page.getByRole("button", { name: /sign out/i });
    await expect(signOut).toBeVisible();

    await signOut.scrollIntoViewIfNeeded();
    await signOut.evaluate((button: HTMLButtonElement) => button.click());
    await page.waitForURL(/\/login/, { timeout: 15_000 });

    await loginViaUi(page, credentials);
    await expect(page.getByTestId("project-switcher-trigger")).toBeVisible();
  });
});
