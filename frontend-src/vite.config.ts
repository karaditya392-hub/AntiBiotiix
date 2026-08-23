import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

/**
 * The build lands in ../frontend, which is exactly where the FastAPI app already
 * looks: it mounts that directory at /static and serves its index.html at "/".
 * Nothing in backend/app.py changes as a result of this migration.
 *
 * `base` is therefore /static/, so the emitted index.html requests its bundle
 * from /static/assets/... rather than /assets/..., which the mount would not serve.
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  base: "/static/",
  build: {
    outDir: path.resolve(__dirname, "../frontend"),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    // Dev-server only. The app calls same-origin relative paths ("" + /api/...),
    // exactly as the original frontend did, so in production no proxy exists and
    // no API base URL is introduced anywhere.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
