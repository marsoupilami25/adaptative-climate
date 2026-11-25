# Development

## Prerequisites

| Tool | Version | Used for | Install |
|---|---|---|---|
| Linux, or WSL2 on Windows | Ubuntu 26.04 tested | everything below | |
| git | | the repository | `sudo apt install git` |
| uv | 0.13 or later | the Python venvs | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.14 | Home Assistant and the tests | installed by uv: `uv python install 3.14` |
| Node.js, npm | Node 24 or later, npm 11 or later | building the card (`frontend/`) | [nvm](https://github.com/nvm-sh/nvm): `nvm install 24` |
| Chromium of Playwright, with its system libraries | the one of `frontend/package.json` | the component tests of the card | below ([Card](#card)) |
| VS Code | | optional: the Testing tab | extensions Python (`ms-python.python`) for the integration, Vitest (`vitest.explorer`) for the card, installed in WSL |

On WSL, the npm of Windows may come first in the `PATH`. Check that Node and
npm are those of Linux:

```bash
command -v node npm    # must show ~/.nvm/versions/node/...
```

## Dev environment

Everything outside the repository lives in `~/ha-dev`:

```text
~/ha-dev/
  .venv/              Home Assistant 2026.11.3 that runs the manual tests
  .venv-test/         the tests on Home Assistant 2026.11.3
  .venv-test-2026.6/  the tests on Home Assistant 2026.6.0, the minimum (tests/integration/compat)
  config/             the configuration of that Home Assistant; its files are links to tests/integration/manual/config
                      and tests/card/manual/config (packages/ and dashboards/: one link per file)
```

To create it:

```bash
mkdir -p ~/ha-dev && cd ~/ha-dev
uv venv .venv --python 3.14
uv pip install --python .venv/bin/python homeassistant==2026.11.3
uv venv .venv-test --python 3.14
uv pip install --python .venv-test/bin/python -r <repo>/requirements_test.txt
<repo>/tests/integration/compat/run.sh --collect-only -q    # creates .venv-test-2026.6
<repo>/tests/integration/manual/link_config.sh ~/ha-dev/config
<repo>/tests/card/manual/link_config.sh ~/ha-dev/config
```

## Card

The sources of the card are in `frontend/`
([CARD_ARCHITECTURE.md §8](../documents/CARD_ARCHITECTURE.md#8-build)):

```bash
cd frontend
npm install          # once, and after each change of package.json
npm run build        # → custom_components/adaptative_climate/frontend/adaptative-climate-card.js
npm run watch        # builds again on each change (debug build, with source map)
npm run typecheck
npm test             # the tests of the card (tests/card)
```

The component tests run in the Chromium of Playwright. Once, and after each
change of the version of Playwright:

```bash
cd frontend
npx playwright install chromium               # the browser, in ~/.cache/ms-playwright
sudo env "PATH=$PATH" npx playwright install-deps chromium   # its system libraries (apt)
```

`sudo` resets the `PATH`: `env "PATH=$PATH"` gives it the one with the Node
of nvm.

`frontend/.npmrc` does not run the install scripts of the dependencies. The
build is not in git: the CI makes it for a release
([ARCHITECTURE.md ARCH-15](../documents/ARCHITECTURE.md#arch-15)).

## Release

A release is a tag `vX.Y.Z` ([ARCHITECTURE.md §13](../documents/ARCHITECTURE.md#13-card-and-release)).
From a clean working tree, on `main`:

```bash
cd frontend
npm run release -- minor     # or major, patch, X.Y.Z
git push --follow-tags
```

`npm run release` sets the new version in `frontend/package.json`,
`frontend/package-lock.json` and `manifest.json` (the same everywhere,
ARCH-14), then makes the commit `vX.Y.Z` and the annotated tag `vX.Y.Z`.
`git push --follow-tags` pushes both. The tag starts `release.yml`: the
tests, the check of the version, the build of the card, and the zip
`adaptative_climate.zip` (the content of `custom_components/adaptative_climate/`,
card included) attached to the GitHub release, created when there is none.
HACS installs that zip (`zip_release` in `hacs.json`).

When the workflow fails, no release is made. Fix, commit, then move the tag:
`git tag -d vX.Y.Z`, `git push origin :refs/tags/vX.Y.Z`,
`git tag -a vX.Y.Z -m vX.Y.Z`, `git push --follow-tags`.

### On `main`, or through a pull request

The tag must be on a commit of `main`: it is what HACS installs. The release
runs the tests again on that commit, whatever the way it came.

- **Work on `main`** (today: one developer, `main` not protected): run
  `npm run release` on `main`, then `git push --follow-tags`. The commit of
  the version and its tag go to `main` together.
- **Work through pull requests** (several developers, or `main` protected):
  `npm run release` cannot be used as is. A protected `main` refuses the push
  of the commit; and a tag made on a branch points to a commit that is not on
  `main` once the pull request is merged by *squash* or *rebase*. Then:
  1. on the branch, change the version only, without the tag (an option
     `--no-tag` to add to `scripts/release.mjs`), and merge the pull request;
  2. on `main` up to date, tag the merge: `git tag -a vX.Y.Z -m vX.Y.Z`,
     then `git push --follow-tags`.

## Tests

- The integration: [tests/integration/README.md](../tests/integration/README.md).
  What each type of test checks, and why: [documents/TESTS.md](../documents/TESTS.md).
- The card: [tests/card/README.md](../tests/card/README.md).
  What each type of test checks, and why: [documents/CARD_TESTS.md](../documents/CARD_TESTS.md).
