import path from "path";
import { fileURLToPath } from "url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const buildCommit = process.env.VERCEL_GIT_COMMIT_SHA ?? "local";

// Keep JS/CSS as hashed assets instead of inlining the full application into
// index.html. Vercel can cache /assets/* immutably, which is especially useful
// for repeat visits over higher-latency networks.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __BUILD_COMMIT__: JSON.stringify(buildCommit),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
