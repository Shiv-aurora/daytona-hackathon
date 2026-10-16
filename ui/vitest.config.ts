import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
      // Server-only modules are tested directly; the guard itself only matters to the Next bundler.
      "server-only": fileURLToPath(new URL("./lib/testing/empty.ts", import.meta.url)),
    },
  },
  test: { include: ["**/*.test.{ts,tsx}"], exclude: ["node_modules/**", ".next/**"] },
});
