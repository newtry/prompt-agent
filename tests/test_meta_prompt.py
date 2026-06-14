"""Tests for core/meta_prompt.py — the agent's own system prompts."""

from __future__ import annotations

from prompt_agent.core.meta_prompt import DIAGNOSE_META_PROMPT, META_PROMPT


def test_meta_prompt_non_empty() -> None:
    assert META_PROMPT
    assert len(META_PROMPT) > 500


def test_meta_prompt_has_required_sections() -> None:
    for marker in ["# Role", "# Workflow", "# Output Format", "JSON"]:
        assert marker in META_PROMPT


def test_meta_prompt_has_checklist() -> None:
    # All 10 checklist items should be referenced
    for i in range(1, 11):
        assert f"{i}." in META_PROMPT


def test_meta_prompt_has_few_shot_example() -> None:
    assert "Example" in META_PROMPT
    assert "```json" in META_PROMPT


def test_diagnose_meta_prompt_non_empty() -> None:
    assert DIAGNOSE_META_PROMPT
    assert len(DIAGNOSE_META_PROMPT) > 500


def test_diagnose_meta_prompt_has_required_sections() -> None:
    for marker in ["# Role", "Workflow", "Output Format", "issue", "replacement"]:
        assert marker in DIAGNOSE_META_PROMPT


def test_diagnose_meta_prompt_has_example() -> None:
    assert "Example" in DIAGNOSE_META_PROMPT
    assert "issues" in DIAGNOSE_META_PROMPT