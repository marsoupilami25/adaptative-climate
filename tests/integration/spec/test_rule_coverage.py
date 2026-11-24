"""Every rule of the spec is checked by a spec test, or justified in not_observable.md."""

from __future__ import annotations

from tests.integration.spec import rule_coverage


def test_every_rule_is_tested_or_justified(capsys) -> None:  # type: ignore[no-untyped-def]
    """`python tests/integration/spec/rule_coverage.py --all` gives the matrix."""
    status = rule_coverage.main()
    report = capsys.readouterr().out
    assert status == 0, report
