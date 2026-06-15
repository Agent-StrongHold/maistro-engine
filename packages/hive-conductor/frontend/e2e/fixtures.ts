import { test as base, expect } from "@playwright/test";

const test = base.extend({
  page: async ({ browser, baseURL }, use) => {
    const context = await browser.newContext({
      baseURL: baseURL || undefined,
      extraHTTPHeaders: process.env.ACCESS_TOKEN ? {
        "Cookie": `access_token=${process.env.ACCESS_TOKEN}; sid=${process.env.SID || ""}`,
      } : undefined,
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { test, expect };
