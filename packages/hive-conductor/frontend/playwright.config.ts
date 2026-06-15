import { defineConfig } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://10.10.42.100:8101";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: BASE_URL,
    headless: true,
    screenshot: "only-on-failure",
    extraHTTPHeaders: process.env.ACCESS_TOKEN ? {
      "Cookie": `access_token=${process.env.ACCESS_TOKEN}; sid=${process.env.SID || ""}`,
    } : undefined,
  },
});
