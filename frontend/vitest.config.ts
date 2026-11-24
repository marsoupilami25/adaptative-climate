// The tests of the card (CARD_TESTS.md): in tests/card, outside frontend/.
// - unit: the logic, in happy-dom (no browser);
// - component: the elements, in Chromium (Playwright, headless).
// The tests import no package (the globals of Vitest, the elements by their
// relative path): bare imports then resolve from frontend/.

import { playwright } from "@vitest/browser-playwright";
import type { UserConfigFnObject } from "vite";
import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

const base = (viteConfig as UserConfigFnObject)({ mode: "test", command: "serve" });

export default mergeConfig(
  base,
  defineConfig({
    server: { fs: { allow: [".."] } },
    test: {
      globals: true,
      projects: [
        {
          extends: true,
          test: { name: "unit", dir: "../tests/card/unit", environment: "happy-dom" },
        },
        {
          extends: true,
          test: {
            name: "component",
            dir: "../tests/card/component",
            browser: {
              enabled: true,
              headless: true,
              provider: playwright(),
              instances: [{ browser: "chromium" }],
            },
          },
        },
      ],
    },
  }),
);
