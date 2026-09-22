import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/  https://vitest.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    // No `globals: true` — tests import describe/it/expect explicitly from
    // "vitest" rather than relying on injected globals + extra tsconfig
    // `types` wiring for them.
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Dev-only: the frontend always calls relative /api/* paths, proxied
      // to the FastAPI backend (uv run uvicorn api.main:app --reload,
      // localhost:8000). Chosen over CORSMiddleware because production
      // eventually serves the built frontend FROM FastAPI itself (single
      // origin, no cross-origin request ever happens) — this proxy answers
      // "how does the browser reach the API" the same way, instead of
      // solving a dev-only problem that would need undoing later.
      "/api": {
        // 127.0.0.1, not "localhost": Node's DNS resolution of "localhost"
        // can return ::1 (IPv6) first (Node 17+'s default lookup order —
        // confirmed happening on this Windows box: Vite's own dev server,
        // given the same bare "localhost", ends up bound to [::1] only).
        // uvicorn below binds 127.0.0.1 (IPv4) by default with no --host
        // override, so a proxied connection that resolved to ::1 would hit
        // nothing there. Pinning the literal IPv4 address removes that
        // ambiguity outright rather than relying on resolution order.
        //
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ""),
      },
    },
  },
});
