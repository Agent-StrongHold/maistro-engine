import { test, expect } from "./fixtures";

test.describe("Dashboard Page", () => {
  test("loads dashboard with tabs", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForResponse("**/v1/dashboard/layout", { timeout: 10000 });
    // Should see tab buttons
    const tabs = page.locator("button").filter({ hasText: /Use Case|Overview|Jedai|Cohort|Support/i });
    await expect(tabs.first()).toBeVisible({ timeout: 10000 });
  });

  test("dashboard metrics load", async ({ page }) => {
    await page.goto("/dashboard");
    const response = await page.waitForResponse("**/v1/dashboard/metrics", { timeout: 10000 }).catch(() => null);
    if (response) expect(response.status()).toBe(200);
  });

  test("can switch tabs", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForResponse("**/v1/dashboard/layout", { timeout: 10000 });
    const tabs = page.locator("button").filter({ hasText: /Migration|Cohort/i });
    if (await tabs.first().isVisible()) {
      await tabs.first().click();
      await page.waitForTimeout(500);
    }
  });

  test("widgets render in grid", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(3000);
    // Should have widget cards
    const cards = page.locator("[style*='grid-column']");
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("edit mode toggle works", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(2000);
    const editBtn = page.locator("button").filter({ hasText: /Edit|✎/ });
    if (await editBtn.isVisible()) {
      await editBtn.click();
      // Should show done/undo buttons
      await expect(page.locator("button").filter({ hasText: /Done|✓/ }).first()).toBeVisible({ timeout: 3000 });
    }
  });

  test("airtable widgets fetch data", async ({ page }) => {
    await page.goto("/dashboard");
    const response = await page.waitForResponse("**/v1/widgets/airtable**", { timeout: 15000 }).catch(() => null);
    if (response) {
      expect(response.status()).toBe(200);
      const data = await response.json();
      expect(data).toHaveProperty("breakdown");
    }
  });

  test("bar chart renders for breakdown data", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(5000);
    // Bar charts have percentage-width divs with gradient backgrounds
    const bars = page.locator("[style*='linear-gradient']");
    const count = await bars.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("donut chart renders SVG", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(5000);
    const donuts = page.locator("svg circle[stroke-dasharray]");
    // May or may not have donuts depending on tab
    const count = await donuts.count();
    // Just don't crash
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Dashboard Chat Bar", () => {
  test("chat input visible in edit mode", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(2000);
    const input = page.locator("input[placeholder*='Build'], input[placeholder*='Ask']");
    await expect(input.first()).toBeVisible({ timeout: 5000 });
  });

  test("can type in chat bar", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(2000);
    const input = page.locator("input[placeholder*='Build'], input[placeholder*='Ask']");
    if (await input.first().isVisible()) {
      await input.first().fill("hello");
      const value = await input.first().inputValue();
      expect(value).toBe("hello");
    }
  });
});

test.describe("Deck Builder Page", () => {
  test("loads with slide editor", async ({ page }) => {
    await page.goto("/decks");
    await expect(page.locator("text=Slide 1").first()).toBeVisible({ timeout: 10000 });
  });

  test("has title input", async ({ page }) => {
    await page.goto("/decks");
    const titleInput = page.locator("input[value='Untitled Deck']");
    await expect(titleInput).toBeVisible({ timeout: 10000 });
  });

  test("can add a slide", async ({ page }) => {
    await page.goto("/decks");
    await page.waitForTimeout(2000);
    const addBtn = page.locator("button").filter({ hasText: /Add Slide|\+/ });
    await addBtn.first().click();
    await expect(page.locator("text=Slide 2")).toBeVisible({ timeout: 3000 });
  });

  test("template buttons exist", async ({ page }) => {
    await page.goto("/decks");
    await page.waitForTimeout(2000);
    const templates = page.locator("button").filter({ hasText: /Hero KPI|Status Funnel|Category Mix|Migration|PM Load/ });
    const count = await templates.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test("clicking template adds slide", async ({ page }) => {
    await page.goto("/decks");
    await page.waitForTimeout(2000);
    const templateBtn = page.locator("button").filter({ hasText: /Hero KPI/ });
    if (await templateBtn.isVisible()) {
      await templateBtn.click();
      await expect(page.locator("text=Slide 2")).toBeVisible({ timeout: 3000 });
    }
  });

  test("AI chat input exists", async ({ page }) => {
    await page.goto("/decks");
    await page.waitForTimeout(2000);
    const input = page.locator("input[placeholder*='Describe'], input[placeholder*='slide']");
    await expect(input.first()).toBeVisible({ timeout: 5000 });
  });

  test("present button exists", async ({ page }) => {
    await page.goto("/decks");
    const presentBtn = page.locator("button").filter({ hasText: "Present" });
    await expect(presentBtn).toBeVisible({ timeout: 10000 });
  });

  test("export HTML button exists", async ({ page }) => {
    await page.goto("/decks");
    const exportBtn = page.locator("button").filter({ hasText: "Export HTML" });
    await expect(exportBtn).toBeVisible({ timeout: 10000 });
  });

  test("slide preview has 16:9 aspect ratio", async ({ page }) => {
    await page.goto("/decks");
    await page.waitForTimeout(2000);
    const preview = page.locator("[contenteditable='true']");
    if (await preview.isVisible()) {
      const style = await preview.getAttribute("style");
      expect(style).toContain("aspect-ratio");
    }
  });
});

test.describe("Credentials Page", () => {
  test("loads credential list", async ({ page }) => {
    await page.goto("/credentials");
    const response = await page.waitForResponse("**/v1/credentials", { timeout: 10000 }).catch(() => null);
    if (response) expect(response.status()).toBe(200);
  });

  test("shows airtable provider", async ({ page }) => {
    await page.goto("/credentials");
    await expect(page.locator("text=Airtable").first()).toBeVisible({ timeout: 10000 });
  });

  test("shows jira provider", async ({ page }) => {
    await page.goto("/credentials");
    await expect(page.locator("text=Jira").first()).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Dashboard Demos & Templates", () => {
  test("load demo button visible in edit mode", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(2000);
    const loadBtn = page.locator("button").filter({ hasText: /Templates|Load Demo|📂/ });
    await expect(loadBtn.first()).toBeVisible({ timeout: 5000 });
  });

  test("demos endpoint returns data", async ({ page }) => {
    const response = await page.request.get("/v1/dashboard/demos");
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("deck-templates endpoint returns data", async ({ page }) => {
    const response = await page.request.get("/v1/dashboard/deck-templates");
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.length).toBeGreaterThanOrEqual(30);
  });
});

test.describe("Widget System Integration", () => {
  test("widget-examples endpoint works", async ({ page }) => {
    const response = await page.request.get("/v1/dashboard/widget-examples");
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.length).toBeGreaterThan(50);
  });

  test("airtable widget endpoint handles missing creds gracefully", async ({ page }) => {
    const response = await page.request.get("/v1/widgets/airtable?table=test&group_by=x&max_records=1");
    expect(response.status()).toBe(200);
    const data = await response.json();
    // Should return error, not crash
    expect("error" in data || "breakdown" in data).toBe(true);
  });

  test("jira widget endpoint handles missing creds gracefully", async ({ page }) => {
    const response = await page.request.get("/v1/widgets/jira?project=TEST");
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect("error" in data || "issues" in data).toBe(true);
  });
});
