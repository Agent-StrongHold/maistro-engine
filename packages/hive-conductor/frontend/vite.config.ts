import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = "http://127.0.0.1:8101";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": { target: api, changeOrigin: true },
      "/health": { target: api, changeOrigin: true },
    },
  },
});
