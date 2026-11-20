# Rules the spec tests cannot observe

The spec tests see the integration through Home Assistant only
(`documents/TESTS.md` §2). The rules below cannot be observed that way: they
are covered as said in the last column. `rule_coverage.py` reads the first
column.

| Rule | Why it cannot be observed from outside | Covered by |
|---|---|---|
| ENT-HA-2 | It is about the test runs themselves: the suites run on a version before 2026.11 and on one from 2026.11. | `dev/compat` (job `compat` of the CI) |
| SRC-DATA-5 | A stored value that is not valid is dropped: testing it means writing invalid stored data, whose format belongs to the architecture (`ARCHITECTURE.md` §7). | unit tests of `core/source/storage.py` |
