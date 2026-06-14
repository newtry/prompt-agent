"""Configuration loading with priority: env > project > global."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

GLOBAL_CONFIG_PATH = Path.home() / ".prompt-agent" / "config.toml"
PROJECT_CONFIG_PATH = Path.cwd() / ".prompt-agent.toml"


@dataclass
class LLMConfig:
    default_model: str = "claude-opus-4-7"
    judge_model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"


@dataclass
class SearchConfig:
    enabled: bool = True


@dataclass
class EvalConfig:
    parallel: int = 5
    max_tokens: int = 4096


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    eval: EvalConfig = field(default_factory=EvalConfig)


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _apply_dict(cfg: Config, data: dict) -> None:
    if "llm" in data:
        for k, v in data["llm"].items():
            setattr(cfg.llm, k, v)
    if "search" in data:
        for k, v in data["search"].items():
            setattr(cfg.search, k, v)
    if "eval" in data:
        for k, v in data["eval"].items():
            setattr(cfg.eval, k, v)


def _apply_env(cfg: Config) -> None:
    """Environment variables override file config."""
    if model := os.getenv("PA_DEFAULT_MODEL"):
        cfg.llm.default_model = model
    if model := os.getenv("PA_JUDGE_MODEL"):
        cfg.llm.judge_model = model
    if enabled := os.getenv("PA_SEARCH_ENABLED"):
        cfg.search.enabled = enabled.lower() in ("1", "true", "yes")


def load_config() -> Config:
    """Load configuration with priority: env > project > global."""
    cfg = Config()
    _apply_dict(cfg, _load_toml(GLOBAL_CONFIG_PATH))
    _apply_dict(cfg, _load_toml(PROJECT_CONFIG_PATH))
    _apply_env(cfg)
    return cfg


def ensure_global_dirs() -> Path:
    """Ensure ~/.prompt-agent/ exists. Returns the path."""
    base = Path.home() / ".prompt-agent"
    (base / "library").mkdir(parents=True, exist_ok=True)
    return base