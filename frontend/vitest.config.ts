// Vitest's helper for writing its configuration.
import { defineConfig } from "vitest/config";
// Node's path tools (the "node:" prefix means a built-in module).
import path from "node:path";

export default defineConfig({
  // Make "@/something" in imports point at the frontend folder (matches the tsconfig setting).
  resolve: { alias: { "@": path.resolve(__dirname) } },
  // Run tests in plain Node (no browser) and pick up only the test files inside lib/.
  test: { environment: "node", include: ["lib/**/*.test.ts"] },
});
