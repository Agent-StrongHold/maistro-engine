import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://10.10.42.100:8101",
    headless: true,
    screenshot: "only-on-failure",
  },
});
