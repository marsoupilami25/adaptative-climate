# Compatibility tests

The spec tests (`dev/spec`) and the unit tests (`dev/unit`), run on a
version of Home Assistant before 2026.11: ENT-HA-2 asks that both the
`native_*` path (from 2026.11) and the former one are checked.

| | Current | Compatibility |
|---|---|---|
| Home Assistant | 2026.11.2 | 2026.6.0 |
| Python | 3.14 | 3.14 |
| pytest plugin | `pytest-homeassistant` | `pytest-homeassistant-custom-component==0.13.336` |
| Requirements | `requirements_test.txt` | `dev/compat/requirements.txt` |
| Coverage threshold | 95 % | none |

`pytest-homeassistant` only exists from 2026.11. Before, the plugin is
`pytest-homeassistant-custom-component`, whose versions each pin one Home
Assistant version (0.13.336 = 2026.6.0). The two plugins give the same
helpers under different module names: the tests import them from
`dev/ha_test.py`.

2026.6.0 is the oldest version tested, and the minimum declared in
`hacs.json` (ENT-HA-3).

## Run

```bash
dev/compat/run.sh            # creates ~/ha-dev/.venv-test-2026.6 if needed
dev/compat/run.sh dev/spec   # only the spec tests
```

The CI runs it in the `compat` job of `.github/workflows/tests.yml`.

## In the VS Code Testing tab

VS Code runs the tests of a workspace folder with a single venv: the
`adaptative-climate` folder runs them on 2026.11.2 (`~/ha-dev/.venv-test`).
To see them on 2026.6.0 too, a second folder gives VS Code another path to the
same files, with the compatibility venv:

```text
~/ha-dev/adaptative-climate-2026.6/   outside the repo, not versioned
  custom_components -> <repo>/custom_components
  dev               -> <repo>/dev
  pyproject.toml    -> <repo>/pyproject.toml
  .vscode/settings.json               venv ~/ha-dev/.venv-test-2026.6, pytest on dev/spec and dev/unit
```

`dev/compat/vscode.sh` sets it up:

1. creates or updates the venv `~/ha-dev/.venv-test-2026.6`, as `run.sh` does;
2. creates the folder, its links and its `settings.json`;
3. adds the folder to the workspace `~/ha-dev/ha-dev.code-workspace`, or, if it
   can't, says to add it with *File > Add Folder to Workspace...*

Then, in VS Code: *Developer: Reload Window*. The Testing tab shows one root
per folder, with the same tests under each:

| Root | Python | Home Assistant |
|---|---|---|
| `adaptative-climate` | 3.14 | 2026.11.2 |
| `adaptative-climate-2026.6` | 3.14 | 2026.6.0 |

### In a new dev environment

The folder and its links are not in the repo: a new clone, a new machine or a
new `~/ha-dev` doesn't have them. Run `dev/compat/vscode.sh` again, then reload
the window.

The script can be run again at any time: it rewrites the links and the
`settings.json`, so don't edit that file by hand. To put things elsewhere:
`FOLDER=`, `WORKSPACE=`, `VENV=`.

If the tests come to use another top-level item of the repo, add it to the
links in `vscode.sh` and run it again.

### Good to know

- A file opened from the 2026.6 tree opens through the link: it is another tab
  than the same file opened from the repo, but the same file, edits included.
- Search and Quick Open leave out the 2026.6 folder (`search.exclude` in its
  `settings.json`), so that results don't show twice.
- The 2026.6 folder is inside `~/ha-dev`, which is a folder of the workspace
  too (*HA Dev*): its search would go through the links as well and show the
  results twice. `~/ha-dev/.vscode/settings.json` leaves it out; in a new dev
  environment, add this there by hand (`vscode.sh` doesn't), after the settings
  already in the file:

  ```json
  "search.exclude": {
    "adaptative-climate-2026.6": true
  }
  ```
- If a root shows the wrong Python version, a venv was picked by hand for that
  folder (*Python: Select Interpreter*), which outranks `settings.json`: pick
  the right venv again.
