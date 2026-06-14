"""Tests for core/config.py — configuration loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from prompt_agent.core.config import Config, LLMConfig, load_config


def test_default_config() -> None:
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.llm.default_model == "claude-opus-4-7"
    assert cfg.search.enabled is True


def test_env_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PA_DEFAULT_MODEL", "claude-haiku-test")
    monkeypatch.setenv("PA_SEARCH_ENABLED", "false")
    cfg = load_config()
    assert cfg.llm.default_model == "claude-haiku-test"
    assert cfg.search.enabled is False


def test_global_config_loaded(tmp_path: Path, monkeypatch) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        textwrap.dedent("""
            [llm]
            default_model = "claude-test-model"
            judge_model = "claude-test-judge"

            [search]
            enabled = false
        """).strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("prompt_agent.core.config.GLOBAL_CONFIG_PATH", cfg_file)
    cfg = load_config()
    assert cfg.llm.default_model == "claude-test-model"
    assert cfg.llm.judge_model == "claude-test-judge"
    assert cfg.search.enabled is False


def test_env_overrides_file(tmp_path: Path, monkeypatch) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        textwrap.dedent("""
            [llm]
            default_model = "claude-file-model"
        """).strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("prompt_agent.core.config.GLOBAL_CONFIG_PATH", cfg_file)
    monkeypatch.setenv("PA_DEFAULT_MODEL", "claude-env-model")
    cfg = load_config()
    assert cfg.llm.default_model == "claude-env-model"