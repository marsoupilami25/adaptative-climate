# Tests

What each type of test checks, and why: [documents/TESTS.md](../documents/TESTS.md).

```text
dev/
  conftest.py, ha_test.py   shared by the pytest suites (ha_test.py: helpers of the plugin installed)
  spec/                     1. spec tests: black box, through Home Assistant only
    harness/                the bench: devices, sensors, AC entity, flows, Home Assistant instances
  compat/                   2. compatibility: the same suites on Home Assistant 2025.1.0
  unit/                     3. unit tests: white box, per component
  manual/                   4. manual tests: Home Assistant config and dashboards
```

## Spec and unit tests (Home Assistant 2026.11.2)

The venv `~/ha-dev/.venv-test`, from `requirements_test.txt`:

```bash
~/ha-dev/.venv-test/bin/pytest                     # dev/spec and dev/unit
~/ha-dev/.venv-test/bin/pytest dev/spec            # spec tests only
~/ha-dev/.venv-test/bin/pytest -m "spec" -k cfg    # by name
~/ha-dev/.venv-test/bin/pytest --cov --cov-branch  # with coverage
```

Find the tests of a rule: `grep -rn '"ENT-TGT-4"' dev/spec`.

## Compatibility tests (Home Assistant 2025.1.0)

```bash
dev/compat/run.sh           # creates ~/ha-dev/.venv-test-2025.1 if needed
dev/compat/run.sh dev/spec
```

Details: [compat/README.md](compat/README.md).

## VS Code Testing tab

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

These are the tests on Home Assistant 2026.11.2. To see them on 2025.1.0 too,
next to them: run `dev/compat/vscode.sh`, see
[compat/README.md](compat/README.md#in-the-vs-code-testing-tab).

After a settings change: *Developer: Reload Window*.

## Manual tests

[manual/README.md](manual/README.md).
