import { defineConfig, devices } from "@playwright/test";
import { AUTH_FILE } from "./e2e/helpers";

/**
 * Playwright E2E configuration.
 *
 * Runs against the production build served by `vite preview`.
 * The backend must be running at VITE_API_BASE_URL (default http://localhost:8000).
 *
 * Quick local run:
 *   # Terminal 1 — backend
 *   cd backend && uvicorn app.main:app --reload
 *
 *   # Terminal 2 — frontend preview
 *   npm run build && npm run preview
 *
 *   # Terminal 3 — tests
 *   npx playwright test
 */

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:4173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,    // serial to avoid race conditions on shared test DB
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // Allow enough time for API calls to return
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: AUTH_FILE,
      },
      dependencies: ["setup"],
    },
  ],
  // Automatically start/stop the frontend dev server in local mode
  webServer: process.env.CI
    ? undefined
    : {
        command: "npm run build && npm run preview",
        url: BASE_URL,
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
