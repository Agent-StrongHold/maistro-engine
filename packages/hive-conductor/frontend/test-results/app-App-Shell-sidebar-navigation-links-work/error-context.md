# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.spec.ts >> App Shell >> sidebar navigation links work
- Location: e2e/app.spec.ts:10:3

# Error details

```
Error: expect(received).toBeGreaterThanOrEqual(expected)

Expected: >= 8
Received:    0
```

# Page snapshot

```yaml
- generic [ref=e2]: "{\"detail\":\"Not Found\"}"
```

# Test source

```ts
  1   | import { test, expect } from "./fixtures";
  2   | 
  3   | test.describe("App Shell", () => {
  4   |   test("has icon sidebar with bee emoji", async ({ page }) => {
  5   |     await page.goto("/chat");
  6   |     const bee = page.locator(".icon-sidebar").first();
  7   |     await expect(bee).toBeVisible({ timeout: 10000 });
  8   |   });
  9   | 
  10  |   test("sidebar navigation links work", async ({ page }) => {
  11  |     await page.goto("/chat");
  12  |     const navLinks = page.locator("a.nav-icon");
  13  |     const count = await navLinks.count();
> 14  |     expect(count).toBeGreaterThanOrEqual(8);
      |                   ^ Error: expect(received).toBeGreaterThanOrEqual(expected)
  15  |   });
  16  | });
  17  | 
  18  | test.describe("Chat Page", () => {
  19  |   test("shows chat empty state with suggestions", async ({ page }) => {
  20  |     await page.goto("/chat");
  21  |     await expect(page.locator("text=Hive Conductor").first()).toBeVisible({ timeout: 10000 });
  22  |   });
  23  | 
  24  |   test("has message input", async ({ page }) => {
  25  |     await page.goto("/chat");
  26  |     const input = page.locator("input.input-field");
  27  |     await expect(input.first()).toBeVisible({ timeout: 10000 });
  28  |   });
  29  | 
  30  |   test("suggestions are clickable cards", async ({ page }) => {
  31  |     await page.goto("/chat");
  32  |     const cards = page.locator(".card");
  33  |     await expect(cards.first()).toBeVisible({ timeout: 10000 });
  34  |   });
  35  | });
  36  | 
  37  | test.describe("Agents Page", () => {
  38  |   test("loads agents from API", async ({ page }) => {
  39  |     await page.goto("/agents");
  40  |     await expect(page.locator("text=The Hive").first()).toBeVisible({ timeout: 10000 });
  41  |     const response = await page.waitForResponse("**/v1/agents", { timeout: 10000 }).catch(() => null);
  42  |     if (response) expect(response.status()).toBe(200);
  43  |   });
  44  | });
  45  | 
  46  | test.describe("Missions Page", () => {
  47  |   test("loads missions from API", async ({ page }) => {
  48  |     await page.goto("/missions");
  49  |     const response = await page.waitForResponse("**/v1/tasks", { timeout: 10000 }).catch(() => null);
  50  |     if (response) expect(response.status()).toBe(200);
  51  |   });
  52  | });
  53  | 
  54  | test.describe("Skills Page", () => {
  55  |   test("loads skills from API", async ({ page }) => {
  56  |     await page.goto("/skills");
  57  |     const response = await page.waitForResponse("**/v1/skills", { timeout: 10000 }).catch(() => null);
  58  |     if (response) expect(response.status()).toBe(200);
  59  |   });
  60  | });
  61  | 
  62  | test.describe("Schedules Page", () => {
  63  |   test("loads schedules with tabs", async ({ page }) => {
  64  |     await page.goto("/schedules");
  65  |     const response = await page.waitForResponse("**/v1/schedules", { timeout: 10000 }).catch(() => null);
  66  |     if (response) expect(response.status()).toBe(200);
  67  |   });
  68  | });
  69  | 
  70  | test.describe("Memory Page", () => {
  71  |   test("loads memory entries", async ({ page }) => {
  72  |     await page.goto("/memory");
  73  |     const response = await page.waitForResponse("**/v1/memory/entries", { timeout: 10000 }).catch(() => null);
  74  |     if (response) expect(response.status()).toBe(200);
  75  |   });
  76  | });
  77  | 
  78  | test.describe("MCP Page", () => {
  79  |   test("loads MCP servers and tools", async ({ page }) => {
  80  |     await page.goto("/mcp");
  81  |     const response = await page.waitForResponse("**/v1/mcp/servers", { timeout: 10000 }).catch(() => null);
  82  |     if (response) expect(response.status()).toBe(200);
  83  |   });
  84  | });
  85  | 
  86  | test.describe("Containers Page", () => {
  87  |   test("loads containers from API", async ({ page }) => {
  88  |     await page.goto("/containers");
  89  |     const response = await page.waitForResponse("**/v1/containers", { timeout: 10000 }).catch(() => null);
  90  |     if (response) expect(response.status()).toBe(200);
  91  |   });
  92  | });
  93  | 
  94  | test.describe("CLI Page", () => {
  95  |   test("shows terminal with status", async ({ page }) => {
  96  |     await page.goto("/cli");
  97  |     await expect(page.locator("text=CLI").first()).toBeVisible({ timeout: 10000 });
  98  |     await expect(page.locator("text=hctl status").first()).toBeVisible();
  99  |   });
  100 | 
  101 |   test("can type help command", async ({ page }) => {
  102 |     await page.goto("/cli");
  103 |     const input = page.locator("input");
  104 |     await expect(input).toBeVisible({ timeout: 10000 });
  105 |     await input.fill("help");
  106 |     await input.press("Enter");
  107 |     await expect(page.locator("text=hctl status")).toBeVisible({ timeout: 5000 });
  108 |   });
  109 | });
  110 | 
  111 | test.describe("Settings Page", () => {
  112 |   test("loads settings from API", async ({ page }) => {
  113 |     await page.goto("/settings");
  114 |     const response = await page.waitForResponse("**/v1/settings", { timeout: 10000 }).catch(() => null);
```