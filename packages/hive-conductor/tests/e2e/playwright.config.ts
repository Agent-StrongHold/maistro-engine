import { defineConfig } from "@playwright/test";

const baseURL = process.env.HIVE_BASE_URL || "http://localhost:8101";

export default defineConfig({
  testDir: ".",
  timeout: 60000,
  retries: 1,
  workers: 1,
  use: {
    baseURL,
    headless: true,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
  ],
});
