"""Test suite schema and YAML loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TestCase:
    name: str
    input: dict
    expected_behavior: str  # refuse | comply | partial
    criteria: list[str] = field(default_factory=list)
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    case_name: str
    actual_output: str
    behavior_match: bool
    criteria_results: dict[str, bool]
    rule_violations: list[str]
    judge_score: float
    judge_reasoning: str
    overall_pass: bool


@dataclass
class Suite:
    cases: list[TestCase]


def _validate_case(raw: dict, idx: int) -> TestCase:
    if "name" not in raw:
        raise ValueError(f"case #{idx + 1}: missing 'name'")
    if "input" not in raw:
        raise ValueError(f"case {raw['name']!r}: missing 'input'")
    if "expected" not in raw:
        raise ValueError(f"case {raw['name']!r}: missing 'expected'")
    exp = raw["expected"]
    if "behavior" not in exp:
        raise ValueError(f"case {raw['name']!r}: missing 'expected.behavior'")
    if exp["behavior"] not in {"refuse", "comply", "partial"}:
        raise ValueError(
            f"case {raw['name']!r}: expected.behavior must be refuse|comply|partial, got {exp['behavior']!r}"
        )
    return TestCase(
        name=raw["name"],
        input=dict(raw["input"]),
        expected_behavior=exp["behavior"],
        criteria=list(exp.get("criteria", [])),
        must_contain=list(exp.get("must_contain", [])),
        must_not_contain=list(exp.get("must_not_contain", [])),
    )


def load_suite(path: Path) -> Suite:
    """Load a YAML test suite."""
    if not path.exists():
        raise FileNotFoundError(f"Suite file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Suite file must be a YAML list of cases, got {type(raw).__name__}")
    cases = [_validate_case(item, i) for i, item in enumerate(raw)]
    return Suite(cases=cases)