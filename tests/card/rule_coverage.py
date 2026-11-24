"""Which rules of the card spec the tests of the card cover (CARD_TESTS.md).

Reads the rules of documents/CARD_SPEC.md (`- **CARD-PHASE-1** ...`), and the
rules cited by:
- the automatic tests (tests/card/unit, tests/card/component: in the names of
  their describe and it blocks);
- the manual scenarios (tests/card/manual: the dashboard);
- tests/card/not_observable.md, the rules justified as not observable
  (first column of its table).
Prints the rules covered and missing; exits with 1 when a rule is missing.

    python3 tests/card/rule_coverage.py [--all]   (--all: list every rule)
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "documents" / "CARD_SPEC.md"
TESTS = ROOT / "tests" / "card"
RULE = re.compile(r"\bCARD-(?!ARCH-)[A-Z]+-\d+\b")  # CARD-ARCH-n: decisions of CARD_ARCHITECTURE.md
DEFINITION = re.compile(r"^\s*[-*]\s+\*\*(CARD-[A-Z]+-\d+)\*\*", re.M)


def spec_rules() -> list[str]:
    return list(dict.fromkeys(DEFINITION.findall(SPEC.read_text(encoding="utf-8"))))


def cited(pattern: str) -> dict[str, list[str]]:
    """Rule -> the files that cite it."""
    found: dict[str, list[str]] = defaultdict(list)
    for file in sorted(TESTS.glob(pattern)):
        for rule in sorted(set(RULE.findall(file.read_text(encoding="utf-8")))):
            found[rule].append(str(file.relative_to(TESTS)))
    return found


def not_observable() -> set[str]:
    rules: set[str] = set()
    path = TESTS / "not_observable.md"
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if line.startswith("| ") and not line.startswith("| Rule"):
            rules |= set(RULE.findall(line.split("|")[1]))
    return rules


def main() -> int:
    rules = spec_rules()
    automatic = cited("unit/**/*.test.ts") | {}
    for rule, files in cited("component/**/*.test.ts").items():
        automatic.setdefault(rule, []).extend(files)
    manual = cited("manual/**/*.yaml")
    justified = not_observable()
    unknown = sorted((set(automatic) | set(manual) | justified) - set(rules))
    missing = [rule for rule in rules if rule not in automatic and rule not in manual and rule not in justified]
    if "--all" in sys.argv:
        for rule in rules:
            how = [label for label, where in (("auto", automatic), ("manual", manual)) if rule in where]
            how += ["not observable"] if rule in justified else []
            print(f"  {rule:16s} {', '.join(how) or 'MISSING'}")
    print(
        f"{len(rules)} rules: {sum(rule in automatic for rule in rules)} automatic, "
        f"{sum(rule in manual for rule in rules)} manual, {len(justified & set(rules))} not observable, "
        f"{len(missing)} missing"
    )
    for rule in missing:
        print(f"  missing {rule}")
    for rule in unknown:
        print(f"  cited but not in the spec: {rule}")
    return 1 if missing or unknown else 0


if __name__ == "__main__":
    sys.exit(main())
