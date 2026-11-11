import { expect, test } from "@playwright/test";
import { apiGet, expectNoFatalUiError, openProject, pickProjectKey } from "./helpers";

test.describe("Settings and external integrations", () => {
  test("loads the Trello settings page against the real app", async ({ page }) => {
    const projectKey = await pickProjectKey(page);
    await openProject(page, "/settings", projectKey);
    await page.getByRole("tab", { name: /trello integration/i }).click();

    await expect(page.getByText(/Connect a real Trello board/i)).toBeVisible();
    await expect(page.getByLabel(/Trello API key/i)).toBeVisible();
    await expect(page.getByLabel(/Trello API token/i)).toBeVisible();
    await expectNoFatalUiError(page);
  });

  test("loads the integrations hub and shows the real provider cards", async ({ page }) => {
    await page.goto("/integrations");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/Add Integration/i)).toBeVisible();
    await expect(page.getByTestId("connect-trello")).toBeVisible();
    await expect(page.getByTestId("connect-jira")).toBeVisible();
    await expect(page.getByTestId("connect-microsoft")).toBeVisible();
    await expect(page.getByTestId("connect-github")).toBeVisible();
    await expectNoFatalUiError(page);
  });

  test("connects GitHub with a real personal access token", async ({ page }) => {
    const githubToken = process.env.E2E_GITHUB_TOKEN;
    test.skip(!githubToken, "Set E2E_GITHUB_TOKEN to run the live GitHub connection test.");
    const label = `Engineering GitHub ${Date.now()}`;

    await page.goto("/integrations");
    await page.getByTestId("connect-github").click();
    await page.getByPlaceholder("e.g. Engineering GitHub").fill(label);
    await page.getByPlaceholder("github_pat_...").fill(githubToken!);
    await page.getByRole("button", { name: "Connect GitHub" }).click();

    await expect(page.getByText(label)).toBeVisible({ timeout: 30_000 });
    await expectNoFatalUiError(page);
  });

  test("returns a Jira OAuth handoff URL from the real backend", async ({ page }) => {
    await page.goto("/integrations");
    const response = await apiGet<{ authorization_url: string; provider: string }>(
      page,
      "/integrations/oauth/jira/start",
    );

    expect(response.provider).toBe("jira");
    expect(response.authorization_url).toContain("auth.atlassian.com");
    expect(response.authorization_url).toContain("client_id=");
  });

  test("returns a Microsoft Planner OAuth handoff URL from the real backend", async ({ page }) => {
    await page.goto("/integrations");
    const response = await apiGet<{ authorization_url: string; provider: string }>(
      page,
      "/integrations/oauth/microsoft/start",
    );

    expect(response.provider).toBe("microsoft");
    expect(response.authorization_url).toContain("login.microsoftonline.com");
    expect(response.authorization_url).toContain("client_id=");
  });

  test("the Jira connect button initiates the external authorization handoff", async ({ page }) => {
    await page.route("https://auth.atlassian.com/**", (route) => route.abort());
    await page.goto("/integrations");

    const outbound = page.waitForRequest((request) =>
      request.url().includes("auth.atlassian.com/authorize"),
    );
    await page.getByTestId("connect-jira").click();

    const request = await outbound;
    expect(request.url()).toContain("audience=api.atlassian.com");
  });

  test("the Microsoft Planner connect button initiates the external authorization handoff", async ({ page }) => {
    await page.route("https://login.microsoftonline.com/**", (route) => route.abort());
    await page.goto("/integrations");

    const outbound = page.waitForRequest((request) =>
      request.url().includes("login.microsoftonline.com"),
    );
    await page.getByTestId("connect-microsoft").click();

    const request = await outbound;
    expect(request.url()).toContain("oauth2");
  });
});
