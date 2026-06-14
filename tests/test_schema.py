"""Tests for evaluators/schema.py — YAML test suite loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from prompt_agent.evaluators.schema import TestCase, load_suite


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "suite.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_minimal_suite(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
- name: simple test
  input:
    user: "hi"
  expected:
    behavior: refuse
""",
    )
    suite = load_suite(p)
    assert len(suite.cases) == 1
    c = suite.cases[0]
    assert c.name == "simple test"
    assert c.input == {"user": "hi"}
    assert c.expected_behavior == "refuse"
    assert c.criteria == []
    assert c.must_contain == []
    assert c.must_not_contain == []


def test_load_full_suite(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
- name: with everything
  input:
    user: "query"
    context:
      schema: users
  expected:
    behavior: comply
    criteria:
      - criterion one
      - criterion two
    must_contain:
      - "SELECT"
    must_not_contain:
      - "DROP"
""",
    )
    suite = load_suite(p)
    c = suite.cases[0]
    assert c.expected_behavior == "comply"
    assert c.criteria == ["criterion one", "criterion two"]
    assert c.must_contain == ["SELECT"]
    assert c.must_not_contain == ["DROP"]


def test_load_missing_name(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
- input:
    user: "hi"
  expected:
    behavior: refuse
""",
    )
    with pytest.raises(ValueError, match="missing 'name'"):
        load_suite(p)


def test_load_missing_input(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
- name: foo
  expected:
    behavior: refuse
""",
    )
    with pytest.raises(ValueError, match="missing 'input'"):
        load_suite(p)


def test_load_invalid_behavior(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
- name: foo
  input:
    user: "hi"
  expected:
    behavior: maybe
""",
    )
    with pytest.raises(ValueError, match="must be refuse|comply|partial"):
        load_suite(p)


def test_load_nonexistent_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_suite(tmp_path / "missing.yaml")


def test_load_non_list_yaml(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "key: value\n")
    with pytest.raises(ValueError, match="must be a YAML list"):
        load_suite(p)