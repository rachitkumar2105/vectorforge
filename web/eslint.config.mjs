import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // S2: engine-returned strings must never be injected as HTML.
      "react/no-danger": "error",
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "scripts/qa/**"]),
]);
