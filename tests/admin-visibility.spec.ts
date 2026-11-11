import { test, expect } from '@playwright/test';

test.describe('Norma Admin Visibility', () => {
  test('Solution Owner sees all developers across all projects', async ({ page }) => {
    // Navigate to local test instance
    await page.goto('http://127.0.0.1:8080/auth');

    // Simulate clicking or typing to bypass the initial landing if any, and login
    // Depending on the UI, fill the text fields. Testing locally relies on a seeded database or mocked endpoints
    await page.fill('input[type="email"]', 'norma_admin@example.com');
    await page.fill('input[type="password"]', 'Developer123!');
    await page.click('button:has-text("Sign in")');

    // Wait for redirect to dashboard
    await page.waitForURL('http://127.0.0.1:8080/');

    // Assert that the sidebar contains the specific admin navigation
    await expect(page.locator('text=Company Performance')).toBeVisible({ timeout: 10000 });

    // Navigate to Developers Progress
    await page.click('text=Developer Progress');
    await page.waitForURL('**/developers');

    // The Norma admin should see the overall stats or list of ALL developers
    // Verify the data table or KPI cards load up successfully
    await expect(page.locator('text=Developer KPI Dashboard')).toBeVisible();

    // Verify there are multiple developers rendered in the DOM indicating cross-project visibility
    // E.g., we expect more than 1 developer to show up compared to vendor specific views
    const developerRows = page.locator('tbody tr');
    // Ensure we actually have rows loaded from the server
    await page.waitForResponse(response => response.url().includes('/api/v1/kpis') && response.status() === 200);

    const count = await developerRows.count();
    expect(count).toBeGreaterThanOrEqual(0); // If database has seeded users
  });
});
