"""Rule-based evaluators: must_contain / must_not_contain keyword checks."""

from __future__ import annotations

from prompt_agent.evaluators.schema import TestCase


def evaluate_rules(test_case: TestCase, output: str) -> list[str]:
    """Return a list of rule violations. Empty list = pass."""
    violations: list[str] = []
    for keyword in test_case.must_not_contain:
        if keyword in output:
            violations.append(f"must_not_contain violated: {keyword!r}")
    for keyword in test_case.must_contain:
        if keyword not in output:
            violations.append(f"must_contain missing: {keyword!r}")
    return violations