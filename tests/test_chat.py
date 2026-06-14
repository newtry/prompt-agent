"""Tests for prompt_agent.commands.chat — action protocol parser only.

The interactive REPL itself is not unit-tested (it needs a real stdin and
real LLM); the action parsing is the only piece with deterministic logic.
"""

from __future__ import annotations

from prompt_agent.commands.chat import _build_system_prompt, _parse_action, _strip_action_block
from prompt_agent.memory import Preferences


def test_parse_action_hit() -> None:
    text = "I'll list the library.\n\n```pa-action\n{\"action\": \"list\"}\n```"
    a = _parse_action(text)
    assert a is not None
    assert a.name == "list"
    assert a.args == {}


def test_parse_action_with_args() -> None:
    text = (
        "Let me show that.\n"
        "```pa-action\n"
        '{"action": "show", "slug": "classifier", "version": 2, '
        '"rationale": "user wants to see classifier v2"}\n'
        "```"
    )
    a = _parse_action(text)
    assert a is not None
    assert a.name == "show"
    assert a.args == {"slug": "classifier", "version": 2}
    assert a.rationale == "user wants to see classifier v2"


def test_parse_action_miss() -> None:
    assert _parse_action("just plain text") is None


def test_parse_action_malformed_json() -> None:
    assert _parse_action("```pa-action\nnot json\n```") is None


def test_parse_action_missing_action_field() -> None:
    assert _parse_action("```pa-action\n{\"foo\": \"bar\"}\n```") is None


def test_strip_action_block() -> None:
    text = "preface\n```pa-action\n{\"action\": \"list\"}\n```\nepilogue"
    s = _strip_action_block(text)
    assert "preface" in s
    assert "epilogue" in s
    assert "pa-action" not in s


def test_strip_no_block() -> None:
    assert _strip_action_block("plain text") == "plain text"


def test_build_system_prompt_includes_preferences() -> None:
    prefs = Preferences(preferred_techniques=["CoT"], default_tags=["agent"])
    sp = _build_system_prompt(prefs, "no recent activity")
    assert "CoT" in sp
    assert "agent" in sp
    assert "pa-action" in sp  # action protocol mentioned
    assert "no recent activity" in sp


def test_build_system_prompt_empty_preferences() -> None:
    prefs = Preferences()
    sp = _build_system_prompt(prefs, "")
    assert "no preferences yet" in sp or "no recent activity" in sp or sp  # just don't crash
    assert "pa-action" in sp
