# Development

## Prerequisites

| Tool | Version | Used for | Install |
|---|---|---|---|
| Linux, or WSL2 on Windows | Ubuntu 26.04 tested | everything below | |
| git | | the repository | `sudo apt install git` |
| uv | 0.13 or later | the Python venvs | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.14 | Home Assistant and the tests | installed by uv: `uv python install 3.14` |
| Node.js, npm | Node 24 or later, npm 11 or later | building the card (`frontend/`) | [nvm](https://github.com/nvm-sh/nvm): `nvm install 24` |
| VS Code | | optional: the Testing tab | |

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
```

`frontend/.npmrc` does not run the install scripts of the dependencies. The
build is not in git: the CI makes it for a release
([ARCHITECTURE.md ARCH-15](../documents/ARCHITECTURE.md#arch-15)).

## Tests

- The integration: [tests/integration/README.md](../tests/integration/README.md).
- What each type of test checks, and why: [documents/TESTS.md](../documents/TESTS.md).
