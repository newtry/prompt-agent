"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_library(monkeypatch, tmp_path: Path):
    """Redirect ~/.prompt-agent/ to a tmp dir for the test."""
    base = tmp_path / ".prompt-agent"
    base.mkdir()
    (base / "library").mkdir()

    # Patch ensure_global_dirs to return our tmp
    from prompt_agent.core import config
    from prompt_agent.storage import library as lib_module

    monkeypatch.setattr(config, "ensure_global_dirs", lambda: base)
    monkeypatch.setattr(lib_module, "ensure_global_dirs", lambda: base)
    return base / "library"


@pytest.fixture
def api_key(monkeypatch):
    """Provide a fake API key for tests that touch the SDK."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-key-not-used")
    yield "test-key-not-used"