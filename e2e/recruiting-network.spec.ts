import { expect, test, type APIRequestContext } from "@playwright/test";
import {
  apiGetWithToken,
  apiPostWithToken,
  authenticatePageWithToken,
  DEFAULT_PASSWORD,
  expectNoFatalUiError,
  loginViaApi,
  registerCompanyViaApi,
} from "./helpers";

interface Company {
  id: number;
  name: string;
  tenant_type: string;
}

interface Developer {
  id: number;
  name: string;
  username: string;
}

interface VisibilityGrant {
  id: number;
  client_company_id: number;
  status: string;
}

async function createRealClientPartnership(request: APIRequestContext) {
  const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const username = `real_client_${suffix}`;
  const client = await registerCompanyViaApi(request, {
    username,
    email: `${username}@sprintpulse.dev`,
    password: DEFAULT_PASSWORD,
    account_type: "client_admin",
    company_name: `Real Client ${suffix}`,
    company_type: "client",
  });
  expect(client.company_id, "registered client should have a company").not.toBeNull();

  const clientToken = await loginViaApi(request, { username, password: DEFAULT_PASSWORD });
  const vendors = await apiGetWithToken<Company[]>(request, clientToken, "/companies?tenant_type=vendor");
  const hexadev = vendors.find((company) => company.name === "HexaDev");
  expect(hexadev, "seeded HexaDev vendor should exist").toBeTruthy();

  await apiPostWithToken(request, clientToken, "/companies/me/partnerships", {
    vendor_company_id: hexadev!.id,
  });

  return { client, clientToken, vendor: hexadev! };
}

async function getVendorDeveloper(
  request: APIRequestContext,
  vendorToken: string,
  username: string,
) {
  const developers = await apiGetWithToken<Developer[]>(request, vendorToken, "/developers");
  const developer = developers.find((dev) => dev.username === username);
  expect(developer, `seeded developer ${username} should exist`).toBeTruthy();
  return developer!;
}

test.describe("B2B Recruiting Network with real backend data", () => {
  test("client sees a real partnership and approved developer profile", async ({ page, request }) => {
    const { client, clientToken, vendor } = await createRealClientPartnership(request);
    const vendorToken = await loginViaApi(request, {
      username: "hexadev_admin",
      password: "ChangeMe123!",
    });
    const alice = await getVendorDeveloper(request, vendorToken, "alice");

    const grant = await apiPostWithToken<VisibilityGrant>(
      request,
      vendorToken,
      `/developers/${alice.id}/visibility`,
      { client_company_id: client.company_id },
    );

    const aliceToken = await loginViaApi(request, {
      username: "alice_account",
      password: "Developer123!",
    });
    await apiPostWithToken<VisibilityGrant>(
      request,
      aliceToken,
      `/developers/me/visibility/${grant.id}/approve`,
      {},
    );

    await authenticatePageWithToken(page, clientToken);
    await page.goto("/recruiting-network");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /B2B Recruiting Network/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: vendor.name })).toBeVisible();
    await expect(page.getByText(alice.name)).toBeVisible();
    await expect(page.getByText(`from ${vendor.name}`)).toBeVisible();
    await expectNoFatalUiError(page);
  });
});

test.describe("Developer Client History with real backend data", () => {
  test("developer sees and approves a real pending visibility request", async ({ page, request }) => {
    const { client } = await createRealClientPartnership(request);
    const vendorToken = await loginViaApi(request, {
      username: "hexadev_admin",
      password: "ChangeMe123!",
    });
    const grace = await getVendorDeveloper(request, vendorToken, "grace");

    await apiPostWithToken<VisibilityGrant>(
      request,
      vendorToken,
      `/developers/${grace.id}/visibility`,
      { client_company_id: client.company_id },
    );

    const graceToken = await loginViaApi(request, {
      username: "grace_account",
      password: "Developer123!",
    });
    await authenticatePageWithToken(page, graceToken);
    await page.goto("/developer-history");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /Action Required: Profile Sharing Requests/i })).toBeVisible();
    await expect(page.getByText(`Client Request #${client.company_id}`)).toBeVisible();

    await page.getByRole("button", { name: "Approve" }).click();

    await expect(page.getByText(`Client Request #${client.company_id}`)).toBeHidden();
    await expectNoFatalUiError(page);
  });
});
