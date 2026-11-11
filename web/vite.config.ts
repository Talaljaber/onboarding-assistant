import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Build id shown on the About screen and in /api/health comparisons. The integrator passes the
// git short sha as VITE_BUILD; without it the build is labelled "dev".
const build = process.env.VITE_BUILD || "dev";

const alias = {
  "@": fileURLToPath(new URL("./src", import.meta.url)),
  // The frozen contract fixtures are imported in place, never copied (docs/api_contract.md §8).
  "@fixtures": fileURLToPath(new URL("../contracts/fixtures", import.meta.url)),
};

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: { alias },
  define: { "import.meta.env.VITE_BUILD": JSON.stringify(build) },
  server: {
    fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] },
    // `npm run dev`: same-origin /api calls go to the FastAPI app.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  test: {
    // Threads start faster than forks on Windows.
    pool: "threads",
    maxWorkers: 2,
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
