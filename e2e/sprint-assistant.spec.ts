import { test, expect } from "@playwright/test";

test.describe("Sprint Assistant AI", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to dashboard which should render the Chat Assistant FAB
    await page.goto("/dashboard");
  });

  test("can open the chat assistant and interact", async ({ page }) => {
    // Find the FAB (floating action button) to open assistant. It uses lucide Sparkles icon or Bot icon
    const aiButton = page.getByRole("button", { name: /Open AI Assistant/i }).or(page.locator("button.fixed.bottom-6.right-6"));
    await aiButton.click();

    // Verify the chat window opens
    const chatWindow = page.locator("text=/Sprint Assistant/i").first();
    await expect(chatWindow).toBeVisible();

    await expect(page.getByText(/loading your project data|Ask me anything|I've indexed|Suggestions:/i).first()).toBeVisible({ timeout: 10000 });

    // Click on a suggestion
    const suggestion = page.locator("text=/Which tickets are blocked/i").first();
    if (await suggestion.isVisible()) {
        await suggestion.click();

        // Verify the user message appeared
        await expect(page.locator("text=/Which tickets are blocked/i").last()).toBeVisible();

        // Check if thinking / loading indicator shows, then wait for assistant response
        // Using a generic check since TF-IDF should return something
        await expect(page.locator(".flex.gap-2\\.5").last()).toContainText(/blocked|blockers|No active blockers/i, { timeout: 10000 });
    }
  });
});
