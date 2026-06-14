"""Memory module: cross-session context for prompt-agent.

Three layers, all under ~/.prompt-agent/:

1. preferences.toml   — user-level defaults (style, techniques, tags)
2. evals/<slug>/*.json — per-eval-run records (results, score, reasoning)
3. context.jsonl       — append-only event log (new/edit/eval/diagnose/chat)

The MemoryStore facade ties the three together so commands don't have to
import each submodule individually.
"""

from __future__ import annotations

from .preferences import Preferences, load_preferences, save_preferences
from .eval_history import (
    EvalRun,
    compare_eval_runs,
    list_eval_runs,
    load_eval_run,
    save_eval_run,
)
from .context import ContextEvent, append_event, load_recent_events, summarize_recent
from .store import GLOBAL_MEMORY_DIR, MemoryStore, ensure_global_dirs

__all__ = [
    "GLOBAL_MEMORY_DIR",
    "MemoryStore",
    "Preferences",
    "load_preferences",
    "save_preferences",
    "EvalRun",
    "save_eval_run",
    "load_eval_run",
    "list_eval_runs",
    "compare_eval_runs",
    "ContextEvent",
    "append_event",
    "load_recent_events",
    "summarize_recent",
    "ensure_global_dirs",
]
