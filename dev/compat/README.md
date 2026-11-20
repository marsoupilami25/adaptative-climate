# Compatibility tests

The spec tests (`dev/spec`) and the unit tests (`dev/unit`), run on a
version of Home Assistant before 2026.11: ENT-HA-2 asks that both the
`native_*` path (from 2026.11) and the former one are checked.

| | Current | Compatibility |
|---|---|---|
| Home Assistant | 2026.11.2 | 2025.1.0 |
| Python | 3.14 | 3.13 |
| pytest plugin | `pytest-homeassistant` | `pytest-homeassistant-custom-component==0.13.201` |
| Requirements | `requirements_test.txt` | `dev/compat/requirements.txt` |
| Coverage threshold | 95 % | none |

`pytest-homeassistant` only exists from 2026.11. Before, the plugin is
`pytest-homeassistant-custom-component`, whose versions each pin one Home
Assistant version (0.13.201 = 2025.1.0). The two plugins give the same
helpers under different module names: the tests import them from
`dev/ha_test.py`.

2025.1.0 is the oldest version tested, and the minimum declared in
`hacs.json`. The oldest one possible is 2024.12, which brought the horizontal
swing the spec uses.

## Run

```bash
dev/compat/run.sh            # creates ~/ha-dev/.venv-test-2025.1 if needed
dev/compat/run.sh dev/spec   # only the spec tests
```

The CI runs it in the `compat` job of `.github/workflows/tests.yml`.
