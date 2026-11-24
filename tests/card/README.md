# Tests of the card

What each type of test checks, and why: [documents/CARD_TESTS.md](../../documents/CARD_TESTS.md).
The tools to install first: [dev/README.md](../../dev/README.md).

```text
tests/card/
  tsconfig.json           the types of the tests (npm run typecheck)
  fakes.ts                the AC entity and the hass object of the tests
  unit/                   1. unit tests: the logic, in happy-dom
  component/              2. component tests: the card in Chromium
    harness.ts            the card in a page, with the contexts of the frontend
  manual/                 3. manual tests: the dashboard "Tests card"
    config/packages/card_tests.yaml     declares the dashboard
    config/dashboards/card_tests.yaml   the dashboard and its scenarios
    link_config.sh                      links both into an HA config folder
  rule_coverage.py        each rule of CARD_SPEC.md is covered
  not_observable.md       the rules no test can observe
```

## Automatic tests

From `frontend/`, with the Node of Linux ([dev/README.md](../../dev/README.md#prerequisites)):

```bash
cd frontend
npm test                    # unit and component tests
npm run test:unit
npm run test:component
npx vitest run --project component -t "CARD-DEV-3"    # the tests of a rule
npm run typecheck           # the card and its tests
```

The component tests need Chromium and its system libraries
([dev/README.md](../../dev/README.md#card)).

Find the tests of a rule: `grep -rn 'CARD-DEV-3' tests/card`.

## VS Code Testing tab

The tests of the card show there with the extension
[Vitest](https://marketplace.visualstudio.com/items?itemName=vitest.explorer)
(`vitest.explorer`), installed in WSL. In `.vscode/settings.json` (not
versioned, see [tests/integration/README.md](../integration/README.md#vs-code-testing-tab)),
next to the settings of pytest:

```json
{
  "vitest.rootConfig": "frontend/vitest.config.ts",
  "vitest.nodeExecutable": "/home/<user>/.nvm/versions/node/<version>/bin/node"
}
```

`vitest.nodeExecutable` is the Node of nvm (`command -v node`): VS Code does
not load nvm, and finds the Node of Windows first. Change it after a change
of the version of Node.

After a settings change: *Developer: Reload Window*.

## Compatibility

What the card needs from the frontend exists in Home Assistant 2026.6:

```bash
python3 frontend/scripts/compat-scan.py   # downloads both frontends once into frontend/.cache
```

## Rule coverage

```bash
python3 tests/card/rule_coverage.py         # the rules missing; fails if any
python3 tests/card/rule_coverage.py --all   # how each rule is covered
```

## Manual tests

On the dev instance of Home Assistant (`~/ha-dev`), with the config of the
manual tests of the integration: its entities are the data of these tests.

1. Link the config of the integration, then the one of the card:

   ```bash
   tests/integration/manual/link_config.sh ~/ha-dev/config
   tests/card/manual/link_config.sh ~/ha-dev/config
   ```

   The second script links the package `card_tests.yaml` into
   `config/packages/` and the dashboard into `config/dashboards/`.
2. Build the card: `cd frontend && npm run build`, or `npm run watch` while
   the card changes.
3. Check the config and restart Home Assistant:

   ```bash
   cd ~/ha-dev && .venv/bin/hass --script check_config -c config
   ```

   The dashboard *Tests card* is in the sidebar. A change of the dashboard
   counts at the next refresh of the page; a change of the card, at the next
   refresh after its build.
4. Follow the scenarios of each view. Each one says where it starts
   (**Start**). The resets are those of the dashboards of the integration.
