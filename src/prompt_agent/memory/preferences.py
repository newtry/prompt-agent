"""User preferences — long-lived style/defaults across sessions.

Stored at ~/.prompt-agent/preferences.toml as a plain TOML file.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

from .store import GLOBAL_MEMORY_DIR

PREFERENCES_PATH = GLOBAL_MEMORY_DIR / "preferences.toml"


@dataclass
class Preferences:
    """User-level defaults that pa new / pa chat consult."""

    preferred_techniques: list[str] = field(default_factory=list)
    avoided_techniques: list[str] = field(default_factory=list)
    default_tags: list[str] = field(default_factory=list)
    naming_pattern: str = ""           # e.g. "kebab-case", "snake_case", or "" for auto
    meta_prompt_style: str = "default"  # "default" | "concise" | "verbose"
    chat_persona: str = "concise-zh"     # hint for pa chat
    extra: dict = field(default_factory=dict)


def _dataclass_from_dict(cls, data: dict):
    """tomli_w can't dump unknown fields, so we manually copy known ones."""
    if not isinstance(data, dict):
        return cls()
    field_names = {f.name for f in cls.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in data.items() if k in field_names}
    extra = {k: v for k, v in data.items() if k not in field_names}
    obj = cls(**kwargs)
    if extra:
        obj.extra.update(extra)
    return obj


def load_preferences(path: Path = PREFERENCES_PATH) -> Preferences:
    if not path.exists():
        return Preferences()
    with path.open("rb") as f:
        data = tomllib.load(f)
    return _dataclass_from_dict(Preferences, data)


def save_preferences(prefs: Preferences, path: Path = PREFERENCES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "preferred_techniques": prefs.preferred_techniques,
        "avoided_techniques": prefs.avoided_techniques,
        "default_tags": prefs.default_tags,
        "naming_pattern": prefs.naming_pattern,
        "meta_prompt_style": prefs.meta_prompt_style,
        "chat_persona": prefs.chat_persona,
    }
    if prefs.extra:
        payload.update(prefs.extra)
    with path.open("wb") as f:
        tomli_w.dump(payload, f)
