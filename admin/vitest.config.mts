import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Mirrors tsconfig.json's "@/*" -> "./*" path mapping. Next.js resolves
// that alias itself via its own bundler; plain `vitest run` has no such
// resolution without this, so any test that imports a file under app/ or
// lib/ using the `@/` convention (the norm in this codebase) fails to
// even load, not just to assert.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
});
