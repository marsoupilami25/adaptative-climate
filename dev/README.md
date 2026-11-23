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
  .venv/              Home Assistant 2026.11.2 that runs the manual tests
  .venv-test/         the tests on Home Assistant 2026.11.2
  .venv-test-2026.6/  the tests on Home Assistant 2026.6.0, the minimum (dev/compat)
  config/             the configuration of that Home Assistant; its files are links to dev/manual/config
```

To create it:

```bash
mkdir -p ~/ha-dev && cd ~/ha-dev
uv venv .venv --python 3.14
uv pip install --python .venv/bin/python homeassistant==2026.11.2
uv venv .venv-test --python 3.14
uv pip install --python .venv-test/bin/python -r <repo>/requirements_test.txt
<repo>/dev/compat/run.sh --collect-only -q    # creates .venv-test-2026.6
<repo>/dev/manual/link_config.sh ~/ha-dev/config
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

What each type of test checks, and why: [documents/TESTS.md](../documents/TESTS.md).

```text
dev/
  conftest.py, ha_test.py   shared by the pytest suites (ha_test.py: helpers of the plugin installed)
  spec/                     1. spec tests: black box, through Home Assistant only
    harness/                the bench: devices, sensors, AC entity, flows, Home Assistant instances
  compat/                   2. compatibility: the same suites on Home Assistant 2026.6.0
  unit/                     3. unit tests: white box, per component
  manual/                   4. manual tests: Home Assistant config and dashboards
```

### Spec and unit tests (Home Assistant 2026.11.2)

The venv `~/ha-dev/.venv-test`, from `requirements_test.txt`:

```bash
~/ha-dev/.venv-test/bin/pytest                     # dev/spec and dev/unit
~/ha-dev/.venv-test/bin/pytest dev/spec            # spec tests only
~/ha-dev/.venv-test/bin/pytest -m "spec" -k cfg    # by name
~/ha-dev/.venv-test/bin/pytest --cov --cov-branch  # with coverage
```

Find the tests of a rule: `grep -rn '"ENT-TGT-4"' dev/spec`.

### Compatibility tests (Home Assistant 2026.6.0)

```bash
dev/compat/run.sh           # creates ~/ha-dev/.venv-test-2026.6 if needed
dev/compat/run.sh dev/spec
```

Details: [compat/README.md](compat/README.md).

### VS Code Testing tab

The repo's `.vscode/` is not versioned. In a new dev environment, create
`.vscode/settings.json` at the root of the repo:

```json
{
  "python.defaultInterpreterPath": "/home/<user>/ha-dev/.venv-test/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": ["dev/spec", "dev/unit"]
}
```

These are the tests on Home Assistant 2026.11.2. To see them on 2026.6.0 too,
next to them: run `dev/compat/vscode.sh`, see
[compat/README.md](compat/README.md#in-the-vs-code-testing-tab).

After a settings change: *Developer: Reload Window*.

### Manual tests

[manual/README.md](manual/README.md).
