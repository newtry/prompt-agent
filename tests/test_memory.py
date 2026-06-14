"""Tests for prompt_agent.memory — preferences, eval_history, context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_agent.evaluators.schema import EvalResult
from prompt_agent.memory import (
    ContextEvent,
    EvalRun,
    MemoryStore,
    Preferences,
    append_event,
    compare_eval_runs,
    list_eval_runs,
    load_eval_run,
    load_preferences,
    load_recent_events,
    save_eval_run,
    save_preferences,
    summarize_recent,
)
from prompt_agent.memory.preferences import PREFERENCES_PATH
from prompt_agent.memory.context import CONTEXT_PATH


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


def test_preferences_default(tmp_path: Path, monkeypatch) -> None:
    # Redirect to a tmp path to avoid clobbering real user prefs.
    monkeypatch.setattr(
        "prompt_agent.memory.preferences.PREFERENCES_PATH", tmp_path / "prefs.toml"
    )
    p = load_preferences()
    assert isinstance(p, Preferences)
    assert p.preferred_techniques == []


def test_preferences_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "prompt_agent.memory.preferences.PREFERENCES_PATH", tmp_path / "prefs.toml"
    )
    p = Preferences(
        preferred_techniques=["CoT", "Few-shot"],
        default_tags=["agent"],
        naming_pattern="kebab-case",
        chat_persona="concise-zh",
    )
    save_preferences(p)
    loaded = load_preferences()
    assert loaded.preferred_techniques == ["CoT", "Few-shot"]
    assert loaded.default_tags == ["agent"]
    assert loaded.naming_pattern == "kebab-case"
    assert loaded.chat_persona == "concise-zh"


def test_preferences_extra_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "prompt_agent.memory.preferences.PREFERENCES_PATH", tmp_path / "prefs.toml"
    )
    p = Preferences()
    p.extra["custom_key"] = "custom_value"
    save_preferences(p)
    loaded = load_preferences()
    assert loaded.extra["custom_key"] == "custom_value"


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def test_context_event_invalid_type() -> None:
    with pytest.raises(ValueError, match="invalid event_type"):
        ContextEvent.now("bogus", "summary")


def test_context_append_and_load(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.context.CONTEXT_PATH", tmp_path / "ctx.jsonl")
    append_event(ContextEvent.now("new", "generated foo", slug="foo"))
    append_event(ContextEvent.now("eval", "eval foo: 3/5 pass", slug="foo", pass_rate=0.6))
    events = load_recent_events(10)
    assert len(events) == 2
    assert events[0].event_type == "new"
    assert events[1].event_type == "eval"
    assert events[1].extra["pass_rate"] == 0.6


def test_context_summarize_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.context.CONTEXT_PATH", tmp_path / "ctx.jsonl")
    s = summarize_recent(5)
    assert "No prior activity" in s


def test_context_summarize_recent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.context.CONTEXT_PATH", tmp_path / "ctx.jsonl")
    append_event(ContextEvent.now("new", "generated classifier", slug="classifier"))
    append_event(ContextEvent.now("eval", "eval classifier: 5/5", slug="classifier"))
    s = summarize_recent(5)
    assert "classifier" in s
    assert "[new]" in s
    assert "[eval]" in s


# ---------------------------------------------------------------------------
# Eval history
# ---------------------------------------------------------------------------


def _result(name: str, passed: bool, score: float = 1.0) -> EvalResult:
    return EvalResult(
        case_name=name,
        actual_output="x",
        behavior_match=passed,
        criteria_results={},
        rule_violations=[],
        judge_score=score,
        judge_reasoning="",
        overall_pass=passed,
    )


def test_eval_run_save_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.eval_history.EVAL_HISTORY_DIR", tmp_path / "evals")
    results = [_result("a", True, score=1.0), _result("b", False, score=0.0)]
    run = EvalRun.from_results(
        slug="foo",
        results=results,
        agent_model="m1",
        judge_model="m2",
        suite_path="suite.yaml",
    )
    path = save_eval_run(run)
    assert path.exists()
    runs = list_eval_runs("foo")
    assert len(runs) == 1
    assert runs[0].pass_rate == 0.5
    assert runs[0].avg_score == pytest.approx(0.5)


def test_eval_run_load_specific(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.eval_history.EVAL_HISTORY_DIR", tmp_path / "evals")
    results = [_result("a", True)]
    run = EvalRun.from_results(
        slug="foo",
        results=results,
        agent_model="m1",
        judge_model="m2",
        suite_path="suite.yaml",
    )
    save_eval_run(run)
    loaded = load_eval_run("foo", run.run_id)
    assert loaded.run_id == run.run_id
    assert loaded.slug == "foo"
    assert loaded.results[0]["case_name"] == "a"


def test_eval_run_load_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.eval_history.EVAL_HISTORY_DIR", tmp_path / "evals")
    with pytest.raises(FileNotFoundError):
        load_eval_run("nope", "0000")


def test_compare_eval_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("prompt_agent.memory.eval_history.EVAL_HISTORY_DIR", tmp_path / "evals")
    a = EvalRun.from_results(
        slug="foo",
        results=[_result("c1", True), _result("c2", False)],
        agent_model="m",
        judge_model="m",
        suite_path="s.yaml",
    )
    b = EvalRun.from_results(
        slug="foo",
        results=[_result("c1", True), _result("c2", True)],
        agent_model="m",
        judge_model="m",
        suite_path="s.yaml",
    )
    save_eval_run(a)
    save_eval_run(b)
    cmp = compare_eval_runs("foo", a.run_id, b.run_id)
    assert cmp.improved == ["c2"]
    assert cmp.regressed == []
    assert cmp.pass_rate_delta == pytest.approx(0.5)
