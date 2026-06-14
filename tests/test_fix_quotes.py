"""Tests for _fix_embedded_quotes — the JSON repair state machine."""

from __future__ import annotations

import json

from prompt_agent.evaluators.llm_judge import _fix_embedded_quotes


def test_simple_valid_passthrough() -> None:
    raw = '{"a": "b", "c": "d"}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"a": "b", "c": "d"}


def test_fix_embedded_quote_in_value() -> None:
    raw = '{"reasoning": "agent said "hi" to user"}'
    fixed = _fix_embedded_quotes(raw)
    parsed = json.loads(fixed)
    assert "hi" in parsed["reasoning"]
    assert "'" in parsed["reasoning"]


def test_key_closing_colon_not_modified() -> None:
    """Regression: closing quote followed by : must NOT be replaced."""
    raw = '{"key": "value"}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"key": "value"}


def test_nested_object() -> None:
    raw = '{"a": {"b": "c"}, "d": "e"}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"a": {"b": "c"}, "d": "e"}


def test_array_value() -> None:
    raw = '{"items": ["x", "y", "z"]}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"items": ["x", "y", "z"]}


def test_escaped_quote_preserved() -> None:
    raw = r'{"a": "he said \"hi\""}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"a": 'he said "hi"'}


def test_chinese_chars_unaffected() -> None:
    raw = '{"reasoning": "agent 拒绝了请求"}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"reasoning": "agent 拒绝了请求"}


def test_multiple_embedded_quotes() -> None:
    raw = '{"reasoning": "agent 拒绝了 "测试" 又说 "再见""}'
    fixed = _fix_embedded_quotes(raw)
    parsed = json.loads(fixed)
    assert "'测试'" in parsed["reasoning"]
    assert "'再见'" in parsed["reasoning"]


def test_quote_at_end_of_input_closes_string() -> None:
    """Regression: a quote at end of input should be treated as closing."""
    raw = '{"reasoning": "final value"}'
    fixed = _fix_embedded_quotes(raw)
    assert json.loads(fixed) == {"reasoning": "final value"}


def test_embedded_quote_followed_by_brace_closes() -> None:
    """An embedded quote followed by } should close the string (correct behavior)."""
    raw = '{"reasoning": "ends with embedded quote "}'
    fixed = _fix_embedded_quotes(raw)
    parsed = json.loads(fixed)
    # The trailing " is followed by }, so it closes the string — value is preserved
    assert parsed["reasoning"] == "ends with embedded quote "


def test_extract_json_uses_json_repair_fallback() -> None:
    """_extract_json should still return a dict for severely malformed judge output."""
    from prompt_agent.evaluators.llm_judge import _extract_json
    # Trailing comma + missing quotes around value — only json_repair can fix this
    raw = '{"behavior_match": true, "reasoning": oops}'
    result = _extract_json(raw)
    assert isinstance(result, dict)