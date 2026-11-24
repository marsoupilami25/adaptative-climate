# Adaptative Climate — Tests

How the integration is tested. The spec (`SPEC.md`) says what it does, the
architecture (`ARCHITECTURE.md`) where and how; the tests check both, from
four points of view. How to run them: `tests/integration/README.md`; the tools to install: `dev/README.md`.

## 1. Four types of tests

| Type | Folder | Checks | Point of view | Home Assistant |
|---|---|---|---|---|
| Spec | `tests/integration/spec` | the rules of the spec | black box, through Home Assistant only | 2026.11.3 |
| Compatibility | `tests/integration/compat` | the same behavior on an older Home Assistant (ENT-HA-2) | the spec and unit suites, unchanged | 2026.6.0 |
| Unit | `tests/integration/unit` | the code the spec tests do not reach | white box, per component (`ARCHITECTURE.md` §11) | 2026.11.3 and 2026.6.0 |
| Manual | `tests/integration/manual` | the behavior in a real Home Assistant, on a dashboard | a person, by scenarios | the dev instance |

## 2. Spec tests

They check the spec, and only the spec: nothing of the architecture or of
the code is assumed.

- They do not import the integration (a test checks it). They know the
  names the spec gives: the domain, the entities of §2.1, the attributes of
  §2.2 and §4.1, the options of §3.1, the event and the issues of §4.4.
- They act as the world around the integration does: the user (service
  calls, config flow, options flow, YAML), the devices behind the source
  entities, the sensors, time, Home Assistant restarting.
- They observe what Home Assistant shows: the states and attributes of the
  entities, the calls the devices receive, the Repairs issues, the events,
  the logs.
- They do not read the stored data, nor create config entries by hand:
  the format of both belongs to the architecture. Persistence is checked
  by restarting Home Assistant on the same storage.

The bench (`tests/integration/spec/harness`) gives:

| Part | Role |
|---|---|
| `Device` | the appliance behind a source entity: a real `climate` entity of a test integration. The test plays the device: it obeys the calls (at once, late, never), fails them, or changes on its own (takeover, unavailable, unknown, other capabilities). It keeps running while Home Assistant restarts. |
| `RoomSensor`, `ExternalSensor` | the temperature sensor and the external sensor entities. |
| `AC` | `climate.<name>` and its two monitoring sensors, as shown; the user requests. |
| flows | a user filling the forms of the config flow and the options flow: it knows the option names, not the steps nor the sections. |
| `Bench` | Home Assistant instances one after the other on the same storage (`start`, `restart`, `stop`), the config entries, the time (`advance`), the issues and the events. |

**Traceability.** Each spec test carries the rules it checks,
`@pytest.mark.spec("SRC-STATE-3", ...)`, and the modules follow the sections
of the spec (`test_3_configuration.py`). The rules no spec test can observe
from outside (the inside of the execution model, for instance) are listed
in `tests/integration/spec/not_observable.md`, with the unit tests that cover them.

**A spec test that fails is never changed to fit the code.** A bug of the
code is fixed in the code. A spec that is unclear or contradicts itself is
settled in the spec first.

## 3. Compatibility tests

The spec and the unit suites, run on Home Assistant 2026.6.0, the oldest
version declared (`hacs.json`, ENT-HA-3). From 2026.11, Home Assistant reads the
temperatures of a `climate` entity under `native_*` names; before, under
the former names (ENT-HA-1). Both paths are thus checked. The devices of
the bench give both names too.

The test helpers come from a different plugin before 2026.11
(`pytest-homeassistant-custom-component`, one version per Home Assistant
version): `tests/integration/ha_test.py` imports them from whichever is installed.

## 4. Unit tests

They complete the structural coverage: written after the spec tests, only
for the lines and branches the spec tests do not reach. They follow the
components of the architecture (`tests/integration/unit/core/source/...`):

- `core`: pure Python, with fake ports and a timer port on a manual clock;
  each state machine fed with events; the runtime: order of the steps and
  internal queues (EXEC-1), hooks, loop guard and queue bounds (ARCH-11);
- `config`: schema, checks, builder, fingerprint;
- `ha`: with Home Assistant, the error paths the spec does not reach.

Code that no test can reach is reported as dead code, not covered for the
sake of it. Threshold: 95 % of lines and branches, all suites together.

## 5. Manual tests

A Home Assistant configuration with virtual devices (template climates
driven by helpers) and one dashboard per case, whose scenarios cite the
rules they show. A change of behavior updates the scenarios too. The
dashboards show the entities under test with the card of Adaptative Climate:
it must be built first (`tests/integration/manual/README.md`).

The manual tests of the card share this dev instance and its entities, with
their own dashboard ([CARD_TESTS.md §5](CARD_TESTS.md#5-manual-tests)). The
card has its own tests: [CARD_TESTS.md](CARD_TESTS.md).
