/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend (api.py) answers on :8000; in development the browser talks to Vite only, which passes
// /api on, so the app and the API share one origin and no CORS change is needed in the backend.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5173, proxy: { "/api": API_URL } },
  preview: { port: 4173, proxy: { "/api": API_URL } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});
