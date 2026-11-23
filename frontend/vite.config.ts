// Builds the card into one ES file, in the folder the integration serves
// (CARD_ARCHITECTURE.md §8, ARCHITECTURE.md ARCH-12).
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import pkg from "./package.json" with { type: "json" };

// The copy imports these without ".js", as the Home Assistant frontend does
// with its tsconfig paths (also in tsconfig.json).
const COPY_ALIASES = [
  { find: /^(lit\/decorators|lit\/directives\/[\w-]+|@lit-labs\/observers\/resize-controller)$/, replacement: "$1.js" },
];

export default defineConfig(({ mode }) => ({
  resolve: {
    alias: COPY_ALIASES,
  },
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
