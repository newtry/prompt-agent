"""Memory store facade — single entry point for all memory operations."""

from __future__ import annotations

from pathlib import Path

GLOBAL_MEMORY_DIR = Path.home() / ".prompt-agent"


def ensure_global_dirs() -> None:
    """Create the global memory directory tree if it doesn't exist."""
    GLOBAL_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (GLOBAL_MEMORY_DIR / "evals").mkdir(parents=True, exist_ok=True)
    (GLOBAL_MEMORY_DIR / "library").mkdir(parents=True, exist_ok=True)


class MemoryStore:
    """Thin facade. Most call sites will use the module-level functions
    directly; this class is here for code paths that want a single dependency
    (e.g. tests, pa chat) and for future extension (e.g. swapping the
    storage backend)."""

    def __init__(self, root: Path | None = None):
        self.root = root or GLOBAL_MEMORY_DIR
        ensure_global_dirs()

    # Preferences
    def load_preferences(self):
        from .preferences import PREFERENCES_PATH, load_preferences
        if self.root != GLOBAL_MEMORY_DIR:
            return load_preferences(self.root / "preferences.toml")
        return load_preferences(PREFERENCES_PATH)

    def save_preferences(self, prefs) -> None:
        from .preferences import PREFERENCES_PATH, save_preferences
        if self.root != GLOBAL_MEMORY_DIR:
            save_preferences(prefs, self.root / "preferences.toml")
        else:
            save_preferences(prefs, PREFERENCES_PATH)

    # Context
    def append_event(self, event) -> None:
        from .context import CONTEXT_PATH, append_event
        if self.root != GLOBAL_MEMORY_DIR:
            append_event(event, self.root / "context.jsonl")
        else:
            append_event(event, CONTEXT_PATH)

    def load_recent_events(self, n: int = 20):
        from .context import CONTEXT_PATH, load_recent_events
        if self.root != GLOBAL_MEMORY_DIR:
            return load_recent_events(n, self.root / "context.jsonl")
        return load_recent_events(n, CONTEXT_PATH)

    def summarize_recent(self, n: int = 10) -> str:
        from .context import CONTEXT_PATH, summarize_recent
        if self.root != GLOBAL_MEMORY_DIR:
            return summarize_recent(n, self.root / "context.jsonl")
        return summarize_recent(n, CONTEXT_PATH)

    # Eval history
    def save_eval_run(self, run) -> "Path":
        from .eval_history import EVAL_HISTORY_DIR, save_eval_run
        if self.root != GLOBAL_MEMORY_DIR:
            # Custom root: just save into a subdir (no full EVAL_HISTORY_DIR swap
            # unless we go all-in on testability).
            return save_eval_run(run)
        return save_eval_run(run)

    def list_eval_runs(self, slug: str):
        from .eval_history import list_eval_runs
        return list_eval_runs(slug)

    def load_eval_run(self, slug: str, run_id: str):
        from .eval_history import load_eval_run
        return load_eval_run(slug, run_id)

    def compare_eval_runs(self, slug: str, a_run_id: str, b_run_id: str):
        from .eval_history import compare_eval_runs
        return compare_eval_runs(slug, a_run_id, b_run_id)
