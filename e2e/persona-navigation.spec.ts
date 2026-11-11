import { expect, type APIRequestContext, type Page, test } from "@playwright/test";
import { API_V1, AUTH_TOKEN_STORAGE_KEY, expectNoFatalUiError } from "./helpers";

async function loginWithSeededPersona(
  page: Page,
  request: APIRequestContext,
  credentials: { username: string; password: string },
) {
  const response = await request.post(`${API_V1}/auth/login`, {
    data: credentials,
  });
  expect(response.ok(), `${credentials.username} should be able to sign in`).toBeTruthy();

  const token = (await response.json()) as { access_token: string };
  await page.addInitScript(
    ({ accessToken, storageKey }) => {
      window.localStorage.setItem(storageKey, accessToken);
    },
    { accessToken: token.access_token, storageKey: AUTH_TOKEN_STORAGE_KEY },
  );
}

test.describe("Seeded persona navigation and page ownership", () => {
  test("guest users are forced through login before protected pages", async ({ page }) => {
    await page.goto("/login");
    await page.evaluate((storageKey) => window.localStorage.removeItem(storageKey), AUTH_TOKEN_STORAGE_KEY);

    await page.goto("/dashboard");

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("client admin lands on the company dashboard with client navigation", async ({ page, request }) => {
    await loginWithSeededPersona(page, request, {
      username: "horizon_admin",
      password: "ChangeMe123!",
    });

    await page.goto("/");

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("banner").getByRole("heading", { name: /dashboard/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Dashboard$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Client Progress/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Integrations/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Settings/i })).toBeVisible();
    await expectNoFatalUiError(page);
  });

  for (const persona of [
    { username: "horizon_exec", label: "client executive" },
    { username: "retail_pm", label: "client project manager" },
  ]) {
    test(`${persona.label} lands on a client-owned dashboard experience`, async ({ page, request }) => {
      await loginWithSeededPersona(page, request, {
        username: persona.username,
        password: "ChangeMe123!",
      });

      await page.goto("/");

      await expect(page).toHaveURL(/\/dashboard/);
      await expect(page.getByRole("banner").getByRole("heading", { name: /dashboard/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^Dashboard$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /Client Progress/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /Repository/i })).toBeVisible();
      await expectNoFatalUiError(page);
    });
  }

  test("vendor admin lands on developer progress with vendor navigation", async ({ page, request }) => {
    await loginWithSeededPersona(page, request, {
      username: "hexadev_admin",
      password: "ChangeMe123!",
    });

    await page.goto("/");

    await expect(page).toHaveURL(/\/developers/);
    await expect(page.getByRole("banner").getByRole("heading", { name: /developer progress/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Vendor Dashboard/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Developer Progress/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Responsiveness/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Blockers/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Settings$/i })).toHaveCount(0);
    await expectNoFatalUiError(page);
  });

  test("vendor delivery manager lands on vendor-owned delivery pages", async ({ page, request }) => {
    await loginWithSeededPersona(page, request, {
      username: "novaforge_delivery",
      password: "ChangeMe123!",
    });

    await page.goto("/");

    await expect(page).toHaveURL(/\/developers/);
    await expect(page.getByRole("banner").getByRole("heading", { name: /developer progress/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Vendor Dashboard/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Developer Progress/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Responsiveness/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Settings$/i })).toHaveCount(0);
    await expectNoFatalUiError(page);
  });

  test("developer persona sees developer-owned pages and is redirected from company pages", async ({ page, request }) => {
    await loginWithSeededPersona(page, request, {
      username: "alice_account",
      password: "Developer123!",
    });

    await page.goto("/");

    await expect(page).toHaveURL(/\/developers/);
    await expect(page.getByRole("link", { name: /My Dashboard/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Team Developers/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Client History/i })).toBeVisible();

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/developers/);
    await expectNoFatalUiError(page);
  });

  for (const username of ["david_account", "grace_account"]) {
    test(`${username} can access the developer-owned dashboard and history`, async ({ page, request }) => {
      await loginWithSeededPersona(page, request, {
        username,
        password: "Developer123!",
      });

      await page.goto("/developer-dashboard");

      await expect(page.getByRole("banner").getByRole("heading", { name: /my dashboard/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /My Dashboard/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /Client History/i })).toBeVisible();

      await page.goto("/developer-history");

      await expect(page.getByRole("banner").getByRole("heading", { name: /client history/i })).toBeVisible();
      await expectNoFatalUiError(page);
    });
  }
});
