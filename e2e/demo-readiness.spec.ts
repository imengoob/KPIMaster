import { expect, test, type BrowserContext } from "@playwright/test";
import {
  API_BASE_URL,
  API_V1,
  AUTH_TOKEN_STORAGE_KEY,
  apiGetWithToken,
  expectNoFatalUiError,
  loginViaApi,
  openProject,
  type AuthenticatedUser,
  type ProjectSummary,
} from "./helpers";

interface PaginatedProjects {
  items: ProjectSummary[];
}

const DEMO_PASSWORD = "Password123!";
const DEMO_PROJECT_KEY = "NORM";

const demoAccounts = [
  {
    label: "client",
    username: "norma_admin",
    expectedRole: "client_admin",
    expectedCompany: "Norma",
    landingUrl: /\/dashboard/,
    landingHeading: /dashboard/i,
    routes: [
      { path: "/dashboard", heading: /dashboard/i, content: /Norma Base Project|Sprint|Completion|Delivery/i },
      { path: "/client-progress", heading: /client progress/i, content: /Client Delivery View|Developer delivery status|Delivery note|Import a Trello board/i },
      { path: "/actions", heading: /action center/i, content: /Action Center|No actions in this view|Generate/i },
    ],
  },
  {
    label: "vendor",
    username: "tawssil_admin",
    expectedRole: "esn_admin",
    expectedCompany: "Tawssil",
    landingUrl: /\/developers/,
    landingHeading: /developer progress/i,
    routes: [
      { path: "/vendor-dashboard", heading: /vendor dashboard/i, content: /Vendor Delivery|Team Velocity|Developer|Import a Trello board/i },
      { path: "/developers", heading: /developer progress/i, content: /Developer KPI Dashboard|Manager Alerts|On Track|At Risk|Behind|Import a Trello board/i },
      { path: "/blockers", heading: /blocker/i, content: /Blocker|Escalation|Level|No blockers|Import a Trello board/i },
    ],
  },
  {
    label: "developer",
    username: "hejer_dev",
    expectedRole: "developer",
    expectedCompany: "Tawssil",
    landingUrl: /\/developers/,
    landingHeading: /developer progress/i,
    routes: [
      { path: "/developer-dashboard", heading: /my dashboard/i, content: /Hejer|Personal|Assigned|Progress|No current assignments/i },
      { path: "/developer-history", heading: /client history/i, content: /Client History|Visibility|Norma|Tawssil|No client/i },
      { path: "/my-actions", heading: /action center/i, content: /Action Center|No actions in this view|Generate/i },
    ],
  },
] as const;

async function putTokenInBrowser(context: BrowserContext, token: string) {
  await context.addInitScript(
    ({ accessToken, storageKey }) => {
      window.localStorage.setItem(storageKey, accessToken);
    },
    { accessToken: token, storageKey: AUTH_TOKEN_STORAGE_KEY },
  );
}

test.describe("Client demo deployment readiness", () => {
  test("validates backend health, demo accounts, project scope, and role workflows", async ({ browser, request, baseURL }) => {
    const health = await request.get(`${API_BASE_URL}/health`);
    expect(health.ok(), "backend health endpoint should respond before giving demo access to clients").toBeTruthy();
    const healthBody = await health.json();
    expect(healthBody).toEqual(expect.objectContaining({
      status: "healthy",
      database: true,
      redis: true,
    }));

    for (const account of demoAccounts) {
      const token = await loginViaApi(request, {
        username: account.username,
        password: DEMO_PASSWORD,
      });

      const me = await apiGetWithToken<AuthenticatedUser>(request, token, "/auth/me");
      expect(me.role, `${account.username} should have the expected role`).toBe(account.expectedRole);
      expect(me.company_name, `${account.username} should belong to the expected company`).toBe(account.expectedCompany);
      if (account.expectedRole === "developer") {
        expect(me.developer_id, "developer demo account should be linked to a developer profile").not.toBeNull();
      }

      const projects = await apiGetWithToken<PaginatedProjects>(request, token, "/projects?page_size=100");
      expect(
        projects.items.some((project) => project.key === DEMO_PROJECT_KEY),
        `${account.username} should see the Norma demo project`,
      ).toBeTruthy();

      const context = await browser.newContext({ baseURL });
      await putTokenInBrowser(context, token);
      const page = await context.newPage();
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await expect(page, `${account.username} should land on the correct role home page`).toHaveURL(account.landingUrl);
      await expect(page.getByRole("banner").getByRole("heading", { name: account.landingHeading })).toBeVisible();
      await expectNoFatalUiError(page);

      for (const route of account.routes) {
        await openProject(page, route.path, DEMO_PROJECT_KEY);
        await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible();
        await expect(page.getByText(route.content).first()).toBeVisible();
        await expectNoFatalUiError(page);
      }

      await context.close();
    }
  });
});
