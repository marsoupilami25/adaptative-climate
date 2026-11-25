// npm run release -- <major|minor|patch|X.Y.Z>
//
// A new version everywhere (ARCHITECTURE.md ARCH-14): frontend/package.json,
// frontend/package-lock.json and custom_components/adaptative_climate/manifest.json.
// Then the commit "vX.Y.Z" and the annotated tag vX.Y.Z, as `npm version` does
// at the root of a repository. Push both with `git push --follow-tags`: the tag
// starts the release workflow (.github/workflows/release.yml).

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const packagePath = resolve(frontend, "package.json");
const manifestPath = resolve(root, "custom_components/adaptative_climate/manifest.json");

function fail(message) {
  console.error(message);
  process.exit(1);
}

const bump = process.argv[2] ?? "";
if (!/^(major|minor|patch|\d+\.\d+\.\d+)$/.test(bump)) {
  fail("Usage: npm run release -- <major|minor|patch|X.Y.Z>");
}

const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
if (git("status", "--porcelain", "--untracked-files=no")) {
  fail("Commit your changes first: the release commit holds the new version only.");
}

const version = () => JSON.parse(readFileSync(packagePath, "utf8")).version;
const manifest = readFileSync(manifestPath, "utf8");
if (JSON.parse(manifest).version !== version()) {
  fail(`manifest.json (${JSON.parse(manifest).version}) and package.json (${version()}) differ: align them first.`);
}

// package.json and package-lock.json, by npm itself (the npm that runs this script)
const npm = process.env.npm_execpath ? [process.execPath, [process.env.npm_execpath]] : ["npm", []];
execFileSync(npm[0], [...npm[1], "version", bump, "--no-git-tag-version"], { cwd: frontend, stdio: "inherit" });

const next = version();
writeFileSync(manifestPath, manifest.replace(/("version"\s*:\s*")[^"]*(")/, `$1${next}$2`));

git("add", "frontend/package.json", "frontend/package-lock.json", "custom_components/adaptative_climate/manifest.json");
git("commit", "-m", `v${next}`);
git("tag", "-a", `v${next}`, "-m", `v${next}`);
console.log(`v${next}: committed and tagged. Push both: git push --follow-tags`);
