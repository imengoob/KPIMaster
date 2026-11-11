import fs from "node:fs";
import path from "node:path";
import { test as setup } from "@playwright/test";
import {
  API_V1,
  AUTH_CREDENTIALS_FILE,
  AUTH_FILE,
  AUTH_TOKEN_STORAGE_KEY,
  makeUserCredentials,
} from "./helpers";

setup("register via API and persist authenticated browser state", async ({ page, request }) => {
  const credentials = makeUserCredentials();
  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

  const registerResponse = await request.post(`${API_V1}/auth/register`, {
    data: credentials,
  });
  if (!registerResponse.ok()) {
    throw new Error(`Register failed: ${await registerResponse.text()}`);
  }

  const loginResponse = await request.post(`${API_V1}/auth/login`, {
    data: {
      username: credentials.username,
      password: credentials.password,
    },
  });
  if (!loginResponse.ok()) {
    throw new Error(`Login failed: ${await loginResponse.text()}`);
  }

  const token = (await loginResponse.json()) as { access_token: string };
  await page.goto("/login");
  await page.evaluate(
    ({ accessToken, storageKey }) => {
      window.localStorage.setItem(storageKey, accessToken);
    },
    { accessToken: token.access_token, storageKey: AUTH_TOKEN_STORAGE_KEY },
  );
  await page.goto("/dashboard");

  await page.context().storageState({ path: AUTH_FILE });
  fs.writeFileSync(AUTH_CREDENTIALS_FILE, JSON.stringify(credentials, null, 2));
});
