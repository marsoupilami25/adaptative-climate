# Rules the spec tests cannot observe

The spec tests see the integration through Home Assistant only
(`documents/TESTS.md` §2). The rules below cannot be observed that way: they
are covered as said in the last column. `rule_coverage.py` reads the first
column.

| Rule | Why it cannot be observed from outside | Covered by |
|---|---|---|
| ENT-HA-2 | It is about the test runs themselves: the suites run on a version before 2026.11 and on one from 2026.11. | `tests/integration/compat` (job `compat` of the CI) |
| ENT-HA-3 | A minimum version is a declaration (`hacs.json`), not a behavior. | `tests/integration/compat`: the suites run on 2026.6.0, the minimum (job `compat` of the CI) |
| SRC-DATA-5 | A stored value that is not valid is dropped: testing it means writing invalid stored data, whose format belongs to the architecture (`ARCHITECTURE.md` §7). | `tests/integration/unit/core/test_not_observable.py` |
| ENT-INIT-2 | A stored mode whose source is `UNDISCOVERED` only happens with the stored data of the source lost or corrupted (the rule says so): testing it means writing stored data, whose format belongs to the architecture. | `tests/integration/unit/core/test_not_observable.py` |
| ENT-INIT-5 | What the state management ignores in `INIT`: the start is one stimulus (EXEC-4), so no event can reach the entity in `INIT` from outside. | `tests/integration/unit/core/test_not_observable.py` |
| ENT-DATA-2 | A stored value of the entity that is not valid is dropped: testing it means writing invalid stored data, whose format belongs to the architecture (`ARCHITECTURE.md` §7). | `tests/integration/unit/core/test_not_observable.py` |
| EVT-2 | There is no other kind of exchange than events: a rule on how the integration is built inside. | `tests/integration/unit/core/test_not_observable.py` |
| EVT-3 | Reading a data item triggers nothing: inside the integration. | `tests/integration/unit/core/test_not_observable.py` |
