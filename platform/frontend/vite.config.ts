// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  vite: {
    server: {
      // Development: the page calls /api on its own address, and this forwards it to the
      // backend -- the same single address the browser sees behind Caddy in production.
      // changeOrigin stays false: the backend compares the request's Host with its Origin.
      proxy: {
        "/api": {
          target: process.env["API_PROXY_TARGET"] ?? "http://127.0.0.1:8000",
          changeOrigin: false,
        },
        "/health": {
          target: process.env["API_PROXY_TARGET"] ?? "http://127.0.0.1:8000",
          changeOrigin: false,
        },
      },
    },
  },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});
