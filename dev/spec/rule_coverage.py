"""Which rules of the spec the spec tests check.

Reads the rules of documents/SPEC.md (`- **SRC-STATE-3** ...`), the rules
each spec test carries (`@pytest.mark.spec(...)`), and the rules listed in
dev/spec/not_observable.md. Prints the rules covered, justified, and
missing; exits with 1 when a rule is missing.

    python dev/spec/rule_coverage.py [--all]   (--all: list every rule)
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "documents" / "SPEC.md"
NOT_OBSERVABLE = ROOT / "dev" / "spec" / "not_observable.md"
RULE = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+[a-z]?)\b")
DEFINITION = re.compile(r"^\s*[-*]\s+\*\*([A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+[a-z]?)\*\*", re.M)


def spec_rules() -> list[str]:
    """The rules defined in the spec, in their order."""
    return list(dict.fromkeys(DEFINITION.findall(SPEC.read_text(encoding="utf-8"))))


def not_observable() -> set[str]:
    """The rules justified as not observable (first column of the table)."""
    rules: set[str] = set()
    for line in NOT_OBSERVABLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and not line.startswith("| Rule"):
            rules |= set(RULE.findall(line.split("|")[1]))
    return rules


def tested_rules() -> dict[str, list[str]]:
    """Rule -> spec tests that check it, from a pytest collection."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rules.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "dev/spec",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--spec-rules={out}",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        per_test: dict[str, list[str]] = json.loads(out.read_text(encoding="utf-8"))
    per_rule: dict[str, list[str]] = defaultdict(list)
    for test, rules in per_test.items():
        for rule in rules:
            per_rule[rule].append(test)
    return per_rule


def main() -> int:
    rules = spec_rules()
    tested = tested_rules()
    justified = not_observable()
    unknown = sorted(set(tested) - set(rules))
    missing = [rule for rule in rules if rule not in tested and rule not in justified]
    covered = [rule for rule in rules if rule in tested]
    print(f"{len(rules)} rules: {len(covered)} tested, ", end="")
    print(f"{len([r for r in rules if r in justified and r not in tested])} not observable, ", end="")
    print(f"{len(missing)} missing")
    if "--all" in sys.argv:
        for rule in rules:
            status = (
                f"{len(tested[rule])} tests" if rule in tested else
                "not observable" if rule in justified else "MISSING"
            )
            print(f"  {rule:<14} {status}")
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for rule in missing:
        by_prefix[rule.rsplit("-", 1)[0]].append(rule)
    for prefix, items in by_prefix.items():
        print(f"  missing {prefix}: {', '.join(items)}")
    if unknown:
        print(f"  markers naming no rule of the spec: {', '.join(unknown)}")
    return 1 if missing or unknown else 0


if __name__ == "__main__":
    sys.exit(main())
