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

## Manual tests

[manual/README.md](manual/README.md).
