# Rules of the card that no test can observe

The tests of the card see it in a page, with a `hass` object
([CARD_TESTS.md](../../documents/CARD_TESTS.md)). The rules below cannot be
observed that way: they are covered as said in the last column.
`rule_coverage.py` reads the first column.

| Rule | Why no test can observe it | Covered by |
|---|---|---|
| CARD-GEN-3 | A minimum version is a declaration, not a behavior. | `frontend/scripts/compat-scan.py`: what the card needs exists in the frontend of Home Assistant 2026.6 (CARD_ARCHITECTURE.md §7, CARD_TESTS.md §4). |
| CARD-GEN-4 | A principle of design: the card holds no logic of the integration. | The review of the code against CARD_ARCHITECTURE.md; the tests of each rule, which give the card only the state of the entity. |
