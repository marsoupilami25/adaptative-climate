// Builds the card into one ES file, in the folder the integration serves
// (CARD_ARCHITECTURE.md §8, ARCHITECTURE.md ARCH-12).
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import pkg from "./package.json" with { type: "json" };

export default defineConfig(({ mode }) => ({
  define: {
    __VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    lib: {
      entry: "src/index.ts",
      formats: ["es"],
      fileName: () => "adaptative-climate-card.js",
    },
    outDir: fileURLToPath(
      new URL("../custom_components/adaptative_climate/frontend", import.meta.url),
    ),
    emptyOutDir: true,
    minify: mode !== "debug",
    sourcemap: mode === "debug" ? "inline" : false,
    rollupOptions: {
      output: {
        codeSplitting: false,
      },
    },
  },
}));
