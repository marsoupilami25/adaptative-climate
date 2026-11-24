# Adaptative Climate card — Tests

How the card is tested. [CARD_SPEC.md](CARD_SPEC.md) says what it does,
[CARD_ARCHITECTURE.md](CARD_ARCHITECTURE.md) where and how. How to run the
tests: [tests/card/README.md](../tests/card/README.md). The tools to install:
[dev/README.md](../dev/README.md).

The tests of the card are apart from those of the integration
([TESTS.md](TESTS.md)): their own folder, tools, rule coverage and CI job.

> **Why:** the card and the integration have their own spec. A test of one
> never depends on the code of the other.

## Table of contents

- [1. Four types of tests](#1-four-types-of-tests)
- [2. Unit tests](#2-unit-tests)
- [3. Component tests](#3-component-tests)
- [4. Compatibility](#4-compatibility)
- [5. Manual tests](#5-manual-tests)
- [6. Rule coverage](#6-rule-coverage)

## 1. Four types of tests

| Type | Folder | Checks | Runs in |
|---|---|---|---|
| Unit | `tests/card/unit` | the logic of the card, without an element | Vitest, with happy-dom |
| Component | `tests/card/component` | the elements of the card, in a page | Vitest in browser mode, Chromium headless (Playwright) |
| Compatibility | `frontend/scripts/compat-scan.py` | what the card needs from the frontend exists in Home Assistant 2026.6 | Python, standard library |
| Manual | `tests/card/manual` | the configuration and the look, in a real Home Assistant | a person, on the dashboard *Tests card* |

The automatic tests live outside `frontend/`. The configuration of Vitest
(`frontend/vitest.config.ts`) finds them there, and gives them the
configuration of the build.

## 2. Unit tests

They check the modules of `frontend/src/ac/` that hold no element: the
configuration, the registry, the texts, the layout of the features, the
phase, the monitoring indicators, the icons of the values.

## 3. Component tests

They mount the card in a page, as a dashboard does, and look at what it
shows and what it asks. They act as the user does: press, choose, hover.

The bench:

| Part | Role |
|---|---|
| `tests/card/fakes.ts` | the world of the card: an AC entity with the attributes of [SPEC.md §2.2](SPEC.md#22-attributes-of-the-ac-entity), its two sources, its two [monitoring sensors](SPEC.md#41-monitoring-sensors), and a `hass` object that records the service calls. |
| `tests/card/component/harness.ts` | the card in a page, at a given size and layout. It answers the contexts of the frontend as Home Assistant does ([CARD-ARCH-6](CARD_ARCHITECTURE.md#card-arch-6)). It stands in for the elements used as is (`ha-card`, `ha-icon-button`, `ha-svg-icon`), and records the events the card sends. |

The card only gets the state of the entities, as from Home Assistant.

> **Why:** the card bases its behavior on that state
> ([CARD-GEN-4](CARD_SPEC.md#card-gen-4)). A test that gave it more would hide
> logic duplicated from the integration.

## 4. Compatibility

The component tests do not depend on the version of Home Assistant: they give
the card a `hass` object and stand-ins. The compatibility with the minimum
version ([CARD-GEN-3](CARD_SPEC.md#card-gen-3)) is checked by the scan of
the copy ([CARD_ARCHITECTURE.md §7](CARD_ARCHITECTURE.md#7-update-of-the-copy)).
It compares the card with the sources of the minimum frontend: contexts,
CSS variables, members of `hass`, translation keys, and the interface of the
elements used as is. It fails on anything missing.

It runs at each update of the copy, and in the CI.

> **Why:** these are the parts of the frontend the card relies on. What
> the card does with them is the same in every version, and the component
> tests check it.

## 5. Manual tests

The dashboard *Tests card* holds the scenarios. Each scenario cites the
rules it shows. Its views:

| View | Shows |
|---|---|
| Configuration | the errors, every option |
| Editor | "Add card", the visual editor |
| Editor and YAML | the YAML and the editor give the same configuration; a wrong value in the preview |
| Look | the card next to the thermostat card, in every mode |
| Theme and language | light and dark; English, French and another language |
| Phase | the phases of a bi-source `heat_cool` |
| Modes | the tooltips, the modes not available, the entity `unavailable` |
| Device line | the device unavailable, a foreign mode |
| Dropdown, Icons | the lists in each style, greyed or not |
| Layout | a sections view, at three sizes |
| Masonry | a masonry view: the height is automatic |
| Monitoring, Monitoring details | the four values of `monitoring`; what a press opens |

Each view fits on one screen. Each scenario gives its starting state
(**Start** of the view, or after another scenario), the operations, and
what to expect.

The data are the entities of the manual tests of the integration: its AC
entities, its virtual sources and their helpers. The card adds no entity.

The dashboard is declared by a package, `tests/card/manual/config/packages/card_tests.yaml`.
Home Assistant merges it into the `lovelace` configuration of the integration.
The `packages/` and `dashboards/` folders of the dev config hold one link
per file: the integration and the card each link their own files.

> **Why:** the manual tests of the card change no file of the integration.

The rules the automatic tests cover are shown again by hand when the look
matters: colors, sizes, themes. "Add card" and the editor need a dashboard
that can be edited: a scenario creates it once.

They run on the dev instance only, at the current version of Home Assistant.
The minimum version is covered by the scan ([§4](#4-compatibility)).

## 6. Rule coverage

Each rule of [CARD_SPEC.md](CARD_SPEC.md) is covered by an automatic test,
a manual scenario, or both. `tests/card/rule_coverage.py` checks it.

- An automatic test carries its rules in the names of its `describe` and
  `it` blocks: `it("CARD-DEV-1: ...")`.
- A manual scenario carries them in its title: `**Phase heat** (CARD-PHASE-1, ...)`.
- A rule no test can observe is listed in `tests/card/not_observable.md`,
  with what covers it.

The script fails when a rule is not covered, or when a test cites a rule the
spec does not have. It is the coverage of the card only. The rules of the
integration have their own ([TESTS.md §2](TESTS.md#2-spec-tests)).
