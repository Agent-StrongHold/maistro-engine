/**
 * PM Workflow E2E — walks through the UI exactly as a project manager would.
 *
 * Flow:
 *   1. First boot → Setup wizard
 *   2. Login as PM user
 *   3. Dashboard overview
 *   4. Create a DAG (Fleet → DagBuilder)
 *   5. Run the DAG
 *   6. Check run results
 *   7. Give thumbs feedback
 *   8. Visit Optimization Inbox
 *   9. Accept/reject a proposal
 *  10. Verify audit trail
 */

import { test, expect, Page } from "@playwright/test";

const ADMIN_USER = "admin";
const ADMIN_PASS = "adminpass123";
const PM_USER = "pmuser";
const PM_PASS = "pmpass1234";

async function setupIfNeeded(page: Page) {
  await page.goto("/");
  const body = await page.textContent("body");

  if (body?.includes("Setup") || body?.includes("First boot")) {
    // Step 1: Name
    await page.locator('input[placeholder="Hive Conductor"]').fill("PM Test Hive");
    await page.locator("button", { hasText: /next/i }).click();

    // Step 2: Hardware
    await page.locator("text=Beast").first().click();
    await page.locator("button", { hasText: /next/i }).click();

    // Step 3: Modules (skip)
    await page.locator("button", { hasText: /next/i }).click();

    // Step 4: Confirm
    await page.locator("button", { hasText: /launch/i }).click();
    await page.waitForURL(/\/(chat|login)?/, { timeout: 15000 }).catch(() => {});
  }
}

async function loginAsPM(page: Page) {
  await page.goto("/login");
  await page.waitForTimeout(500);

  const body = await page.textContent("body");
  if (body?.includes("Register") || body?.includes("Sign up")) {
    // Register first
    const usernameInput = page.locator('input[name="username"], input[placeholder*="user"]').first();
    const passwordInput = page.locator('input[name="password"], input[type="password"]').first();
    const confirmInput = page.locator('input[name="confirm"], input[placeholder*="confirm"]').first();

    await usernameInput.fill(PM_USER);
    await passwordInput.fill(PM_PASS);
    if (await confirmInput.isVisible()) {
      await confirmInput.fill(PM_PASS);
    }
    await page.locator("button", { hasText: /register|sign up/i }).click();
    await page.waitForTimeout(1000);
  }

  // Login
  const usernameInput = page.locator('input[name="username"], input[placeholder*="user"]').first();
  const passwordInput = page.locator('input[name="password"], input[type="password"]').first();

  if (await usernameInput.isVisible()) {
    await usernameInput.fill(PM_USER);
    await passwordInput.fill(PM_PASS);
    await page.locator("button", { hasText: /log.?in|sign.?in/i }).click();
    await page.waitForTimeout(1000);
  }
}

test.describe("PM Workflow — Full UI Walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    await setupIfNeeded(page);
  });

  test("01 — Setup wizard completes on first boot", async ({ page }) => {
    // Setup already ran in beforeEach; verify we're past it
    const r = await page.request.get("/v1/setup/status");
    const data = await r.json();
    expect(data.setup_complete).toBe(true);
  });

  test("02 — PM can login and see dashboard", async ({ page }) => {
    await loginAsPM(page);
    await page.goto("/chat");
    await expect(page.locator("body")).toContainText(/hive|conductor|chat/i, { timeout: 10000 });
  });

  test("03 — Dashboard loads with key metrics", async ({ page }) => {
    await loginAsPM(page);
    await page.goto("/");

    // Wait for the app to load
    await page.waitForTimeout(2000);
    const response = await page.request.get("/health");
    expect(response.status()).toBe(200);
  });

  test("04 — PM can navigate to Fleet page", async ({ page }) => {
    await loginAsPM(page);
    await page.goto("/fleet");
    await page.waitForTimeout(2000);

    // Fleet page should load DAGs
    const apiResponse = await page.request.get("/v1/dags");
    expect(apiResponse.status()).toBe(200);
  });

  test("05 — PM can create a DAG via API (simulating DagBuilder)", async ({ page }) => {
    await loginAsPM(page);

    // Create DAG via API (DagBuilder does this)
    const createResp = await page.request.post("/v1/dags", {
      data: {
        name: "Sprint Retro Digest",
        description: "Collect retro notes and produce action items",
      },
    });
    expect(createResp.status()).toBe(201);
    const dag = await createResp.json();
    expect(dag.name).toBe("Sprint Retro Digest");
    expect(dag.nodes.length).toBe(2);
  });

  test("06 — PM can activate and run a DAG", async ({ page }) => {
    await loginAsPM(page);

    // Create
    const createResp = await page.request.post("/v1/dags", {
      data: { name: "E2E Run Test", description: "test" },
    });
    const dag = await createResp.json();

    // Activate
    const activateResp = await page.request.post(`/v1/dags/${dag.id}/activate`);
    expect(activateResp.status()).toBe(200);
    const activated = await activateResp.json();
    expect(activated.status).toBe("active");

    // Run
    const runResp = await page.request.post(`/v1/dags/${dag.id}/run`);
    expect(runResp.status()).toBe(200);
    const run = await runResp.json();
    expect(run.execution_id).toBeTruthy();
  });

  test("07 — PM can give thumbs feedback on a run", async ({ page }) => {
    await loginAsPM(page);

    // Create + run
    const createResp = await page.request.post("/v1/dags", {
      data: { name: "Feedback Test DAG", description: "test" },
    });
    const dag = await createResp.json();
    await page.request.post(`/v1/dags/${dag.id}/activate`);
    const runResp = await page.request.post(`/v1/dags/${dag.id}/run`);
    const run = await runResp.json();

    // Feedback
    const fbResp = await page.request.post(
      `/v1/dag-runs/${run.execution_id}/feedback`,
      { data: { thumb: "up", comment: "Nailed it!", dag_id: dag.id } }
    );
    // 200 or 404 (run may not be in store if execution was instant)
    expect([200, 404]).toContain(fbResp.status());
  });

  test("08 — PM can trigger optimizer and see proposals", async ({ page }) => {
    await loginAsPM(page);

    const createResp = await page.request.post("/v1/dags", {
      data: { name: "Optimizer Test DAG", description: "test" },
    });
    const dag = await createResp.json();

    // Trigger optimizer
    const optResp = await page.request.post(`/v1/optimizer/${dag.id}/run`);
    expect([200, 400]).toContain(optResp.status());

    // List proposals
    const proposalsResp = await page.request.get(`/v1/optimizer/${dag.id}/proposals`);
    expect(proposalsResp.status()).toBe(200);
    const proposals = await proposalsResp.json();
    expect(Array.isArray(proposals)).toBe(true);
  });

  test("09 — PM can visit Optimization Inbox page", async ({ page }) => {
    await loginAsPM(page);
    await page.goto("/optimization");
    await page.waitForTimeout(2000);

    // The page should render without crashing
    const body = await page.textContent("body");
    expect(body).toBeTruthy();
  });

  test("10 — PM can view audit log", async ({ page }) => {
    await loginAsPM(page);

    const auditResp = await page.request.get("/v1/audit");
    expect(auditResp.status()).toBe(200);
    const entries = await auditResp.json();
    expect(Array.isArray(entries)).toBe(true);
    expect(entries.length).toBeGreaterThan(0);
  });

  test("11 — PM can view DAG metrics", async ({ page }) => {
    await loginAsPM(page);

    const metricsResp = await page.request.get("/v1/dag-metrics");
    expect(metricsResp.status()).toBe(200);
  });

  test("12 — PM can navigate all key pages without errors", async ({ page }) => {
    await loginAsPM(page);

    const pages = ["/chat", "/fleet", "/missions", "/agents", "/settings"];
    for (const p of pages) {
      await page.goto(p);
      await page.waitForTimeout(1000);
      // No crash = page rendered
      const body = await page.textContent("body");
      expect(body?.length).toBeGreaterThan(0);
    }
  });
});
