import { expect, type APIRequestContext, Page } from "@playwright/test";

export const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const API_V1 = `${API_BASE_URL}/api/v1`;
export const AUTH_FILE = "playwright/.auth/user.json";
export const AUTH_CREDENTIALS_FILE = "playwright/.auth/user-credentials.json";
export const DEFAULT_PASSWORD = "E2ePassword1!";
export const AUTH_TOKEN_STORAGE_KEY = "kpimaster.authToken";

export interface ProjectSummary {
  id: number;
  name: string;
  key: string;
}

export interface AuthenticatedUser {
  id: number;
  username: string;
  email: string;
  role: string;
  company_id: number | null;
  company_name: string | null;
  developer_id: number | null;
}

interface PaginatedProjects {
  items: ProjectSummary[];
}

interface ClientProgressReport {
  members: Array<{ developer_id: number }>;
}

interface RepoMismatch {
  ticket_id: number;
}

interface BlockerSummary {
  id: number;
}

export function makeUserCredentials() {
  const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  return {
    username: `e2e_${suffix}`,
    email: `e2e_${suffix}@sprintpulse.dev`,
    password: DEFAULT_PASSWORD,
  };
}

export async function loginViaApi(
  request: APIRequestContext,
  credentials: { username: string; password: string },
) {
  const response = await request.post(`${API_V1}/auth/login`, { data: credentials });
  expect(response.ok(), `${credentials.username} should be able to sign in`).toBeTruthy();
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

export async function registerCompanyViaApi(
  request: APIRequestContext,
  input: {
    username: string;
    email: string;
    password: string;
    account_type?: "company_admin" | "client_admin" | "esn_admin";
    company_name: string;
    company_type?: "client" | "vendor";
  },
) {
  const response = await request.post(`${API_V1}/auth/register`, { data: input });
  const bodyText = await response.text();
  expect(
    response.ok(),
    `${input.username} should be registered: ${response.status()} ${bodyText}`,
  ).toBeTruthy();
  return JSON.parse(bodyText) as AuthenticatedUser;
}

export async function authenticatePageWithToken(page: Page, token: string) {
  await page.addInitScript(
    ({ accessToken, storageKey }) => {
      window.localStorage.setItem(storageKey, accessToken);
    },
    { accessToken: token, storageKey: AUTH_TOKEN_STORAGE_KEY },
  );
}

export async function apiGetWithToken<T>(
  request: APIRequestContext,
  token: string,
  endpoint: string,
): Promise<T> {
  const response = await request.get(`${API_V1}${endpoint}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), `GET ${endpoint} should succeed`).toBeTruthy();
  return (await response.json()) as T;
}

export async function apiPostWithToken<T>(
  request: APIRequestContext,
  token: string,
  endpoint: string,
  data: Record<string, unknown>,
): Promise<T> {
  const response = await request.post(`${API_V1}${endpoint}`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.ok(), `POST ${endpoint} should succeed`).toBeTruthy();
  return (await response.json()) as T;
}

export async function registerViaUi(
  page: Page,
  credentials: { username: string; email: string; password: string },
) {
  await page.goto("/register");
  await page.getByLabel("Username").fill(credentials.username);
  await page.getByLabel("Email").fill(credentials.email);
  await page.locator("#password").fill(credentials.password);
  await page.locator("#confirm-password").fill(credentials.password);
  await page.getByRole("button", { name: /create account/i }).click();
  await page.waitForURL(/\/dashboard|\/$/, { timeout: 20_000 });
  await expect(page.getByTestId("project-switcher-trigger")).toBeVisible({ timeout: 20_000 });
}

export async function loginViaUi(
  page: Page,
  credentials: { username: string; password: string },
) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(credentials.username);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard|\/$/, { timeout: 20_000 });
  await expect(page.getByTestId("project-switcher-trigger")).toBeVisible({ timeout: 20_000 });
}

export async function apiGet<T>(page: Page, endpoint: string): Promise<T> {
  if (page.url() === "about:blank") {
    await page.goto("/", { waitUntil: "domcontentloaded" });
  }

  return page.evaluate(
    async ({ url, storageKey }) => {
      const token = window.localStorage.getItem(storageKey);
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(JSON.stringify({ status: response.status, body }));
      }
      return body;
    },
    { url: `${API_V1}${endpoint}`, storageKey: AUTH_TOKEN_STORAGE_KEY },
  );
}

export async function listProjects(page: Page): Promise<ProjectSummary[]> {
  const response = await apiGet<PaginatedProjects>(page, "/projects?page_size=100");
  return response.items;
}

export async function pickProjectKey(page: Page, preferredKeys: string[] = ["PHX", "ATL", "NOV"]) {
  const projects = await listProjects(page);
  const preferred = projects.find((project) => preferredKeys.includes(project.key.toUpperCase()));
  return (preferred ?? projects[0])?.key;
}

export async function pickSecondaryProjectKey(page: Page, currentKey: string) {
  const projects = await listProjects(page);
  return projects.find((project) => project.key !== currentKey)?.key ?? currentKey;
}

export async function pickProjectForClientProgress(page: Page) {
  const projects = await listProjects(page);
  for (const project of projects) {
    const report = await apiGet<ClientProgressReport>(
      page,
      `/developers/client-progress?project_id=${project.id}`,
    );
    if (report.members.length > 0) return project.key;
  }
  return projects[0]?.key;
}

export async function pickProjectForRepository(page: Page) {
  const projects = await listProjects(page);
  for (const project of projects) {
    const mismatches = await apiGet<RepoMismatch[]>(
      page,
      `/repository-mismatches?project_id=${project.id}`,
    );
    if (mismatches.length > 0) return project.key;
  }
  return projects[0]?.key;
}

export async function pickProjectForBlockers(page: Page) {
  const projects = await listProjects(page);
  for (const project of projects) {
    const blockers = await apiGet<BlockerSummary[]>(
      page,
      `/blockers?project_id=${project.id}`,
    );
    if (blockers.length > 0) return project.key;
  }
  return projects[0]?.key;
}

export async function openProject(page: Page, path: string, projectKey?: string) {
  const suffix = projectKey ? `?project=${encodeURIComponent(projectKey)}` : "";
  await page.goto(`${path}${suffix}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
}

export async function expectNoFatalUiError(page: Page) {
  await expect(page.locator('[data-testid="error-state"]')).toHaveCount(0);
  await expect(page.locator("text=Something went wrong")).toHaveCount(0);
}

export async function switchProject(page: Page, projectKey: string) {
  await page.getByTestId("project-switcher-trigger").click();
  await page.getByTestId(`project-option-${projectKey.toLowerCase()}`).click();
}
