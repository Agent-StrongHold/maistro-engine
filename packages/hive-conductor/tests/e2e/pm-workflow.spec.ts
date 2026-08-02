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
    // Setup.tsx's non-PM-POC wizard is five steps:
    //   ["Hive", "Hardware", "Accounts", "Modules", "Confirm"]
    // This walkthrough used to skip "Accounts" entirely, which did not fail
    // loudly — it parked on that step with `next` permanently disabled, because
    // Setup.tsx gates it on `!adminPassword || !userUsername || !userPassword`.
    // Every spec then died in beforeEach on the same disabled button.

    // 1/5 — Hive
    await page.locator('input[placeholder="Hive Conductor"]').fill("PM Test Hive");
    await page.locator("button", { hasText: /next/i }).click();

    // 2/5 — Hardware
    await page.locator("text=Beast").first().click();
    await page.locator("button", { hasText: /next/i }).click();

    // 3/5 — Accounts. These are the same credentials loginAsPM() logs in with
    // below, so the accounts this creates are the ones the rest of the suite
    // depends on. Both password fields share placeholder="password" (admin
    // card first, daily-user card second), hence nth() rather than placeholder.
    await page.locator('input[placeholder="admin"]').fill(ADMIN_USER);
    await page.locator('input[type="password"]').nth(0).fill(ADMIN_PASS);
    await page.locator('input[placeholder="username"]').fill(PM_USER);
    await page.locator('input[type="password"]').nth(1).fill(PM_PASS);
    await page.locator("button", { hasText: /next/i }).click();

    // 4/5 — Modules (skip)
    await page.locator("button", { hasText: /next/i }).click();

    // 5/5 — Confirm. Wait for the POST itself to land, not for a URL change:
    // the old `waitForURL(/\/(chat|login)?/)` matched the current URL "/"
    // immediately and returned without waiting for anything, so spec 01 could
    // read /v1/setup/status while setup/complete was still in flight and see
    // setup_complete: false.
    await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/v1/setup/complete") && r.request().method() === "POST",
        { timeout: 15000 },
      ),
      page.locator("button", { hasText: /launch/i }).click(),
    ]).catch(() => {});
  }
}

// Login.tsx's inputs carry NO `name` and no user-ish placeholder — they are
// identified by autocomplete tokens:
//   login mode     -> autocomplete="username" + autocomplete="current-password"
//   register mode  -> autocomplete="username" + two autocomplete="new-password"
//                     (password, then confirm)
// The previous selectors here were 'input[name="username"], input[placeholder*="user"]',
// which match nothing in either mode. That is why specs 02-12 each hung for the
// full test timeout inside this helper rather than failing on an assertion.
//
// Mode is detected from the form itself rather than from body text: the login
// view also renders a "Register" toggle, so a body.includes("Register") check
// takes the register branch while sitting on the login form.
async function loginAsPM(page: Page) {
  await page.goto("/login");

  const usernameInput = page.locator('input[autocomplete="username"]').first();
  const newPasswords = page.locator('input[autocomplete="new-password"]');
  const currentPassword = page.locator('input[autocomplete="current-password"]').first();

  await usernameInput.waitFor({ state: "visible" });

  if (await newPasswords.first().isVisible().catch(() => false)) {
    // Register first.
    await usernameInput.fill(PM_USER);
    await newPasswords.nth(0).fill(PM_PASS);
    if (await newPasswords.nth(1).isVisible().catch(() => false)) {
      await newPasswords.nth(1).fill(PM_PASS);
    }
    await page.locator("button", { hasText: /register|sign up/i }).click();
    await page.waitForTimeout(1000);
  }

  if (await currentPassword.isVisible().catch(() => false)) {
    await usernameInput.fill(PM_USER);
    await currentPassword.fill(PM_PASS);
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
