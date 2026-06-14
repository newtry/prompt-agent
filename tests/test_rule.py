"""Tests for evaluators/rule.py — keyword rule evaluator."""

from __future__ import annotations

from prompt_agent.evaluators.rule import evaluate_rules
from prompt_agent.evaluators.schema import TestCase


def _case(must_contain=(), must_not_contain=()) -> TestCase:
    return TestCase(
        name="t",
        input={"user": "x"},
        expected_behavior="comply",
        must_contain=list(must_contain),
        must_not_contain=list(must_not_contain),
    )


def test_no_rules_passes() -> None:
    assert evaluate_rules(_case(), "any output") == []


def test_must_contain_present() -> None:
    assert evaluate_rules(_case(must_contain=["hello"]), "say hello world") == []


def test_must_contain_missing() -> None:
    v = evaluate_rules(_case(must_contain=["hello", "world"]), "just hello")
    assert len(v) == 1
    assert "world" in v[0]


def test_must_not_contain_violated() -> None:
    v = evaluate_rules(_case(must_not_contain=["DROP"]), "DROP TABLE users")
    assert len(v) == 1
    assert "DROP" in v[0]


def test_must_not_contain_clean() -> None:
    assert evaluate_rules(_case(must_not_contain=["DROP"]), "SELECT 1") == []


def test_multiple_violations() -> None:
    v = evaluate_rules(
        _case(must_contain=["a", "b"], must_not_contain=["c"]),
        "has a and c",  # b is missing
    )
    assert len(v) == 2  # missing b, contains c