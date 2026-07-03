import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import node from "@astrojs/node";

// Hybrid render: producer/artifact pages are statically generated (SSG) at build
// time; the dashboard / feed / chat / admin pages opt into SSR via
// `export const prerender = false` and hydrated React islands that call the live
// API at request/interaction time.
export default defineConfig({
  output: "static",
  adapter: node({ mode: "standalone" }),
  integrations: [react()],
  server: { port: 4321 },
  vite: {
    // The live API base; the islands read it from PUBLIC_TURING_API.
    define: {
      "import.meta.env.PUBLIC_TURING_API": JSON.stringify(
        process.env.PUBLIC_TURING_API ?? "http://localhost:8120",
      ),
    },
  },
});
