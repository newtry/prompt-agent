"""Cross-session context: append-only event log.

Each event records a user action. `pa chat` reads recent events to inject
context into the LLM system prompt (e.g. "the user has been iterating on a
RAG agent for the last 3 sessions — they prefer few-shot + structured output").

Stored at ~/.prompt-agent/context.jsonl (one JSON object per line).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .store import GLOBAL_MEMORY_DIR

CONTEXT_PATH = GLOBAL_MEMORY_DIR / "context.jsonl"

# Cap the log so it doesn't grow unbounded. 2000 events ≈ 1MB, plenty.
MAX_EVENTS = 2000

VALID_EVENT_TYPES = {"new", "edit", "eval", "diagnose", "fork", "save", "seed_install", "chat"}


@dataclass
class ContextEvent:
    timestamp: str
    event_type: str
    summary: str
    slug: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def now(event_type: str, summary: str, slug: str = "", **extra) -> "ContextEvent":
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"invalid event_type {event_type!r}; must be one of {sorted(VALID_EVENT_TYPES)}"
            )
        return ContextEvent(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            event_type=event_type,
            summary=summary,
            slug=slug,
            extra=extra,
        )


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else CONTEXT_PATH


def append_event(event: ContextEvent, path: Path | None = None) -> None:
    path = _resolve_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(event.to_json() + "\n")
    _maybe_truncate(path)


def _maybe_truncate(path: Path) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= MAX_EVENTS:
        return
    # Keep the most recent MAX_EVENTS lines.
    path.write_text("\n".join(lines[-MAX_EVENTS:]) + "\n", encoding="utf-8")


def load_recent_events(n: int = 20, path: Path | None = None) -> list[ContextEvent]:
    path = _resolve_path(path)
    if not path.exists():
        return []
    out: list[ContextEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            out.append(ContextEvent(**data))
        except (json.JSONDecodeError, TypeError):
            continue
    return out[-n:]


def summarize_recent(n: int = 10, path: Path | None = None) -> str:
    """Produce a one-paragraph natural-language summary for LLM context.

    Format: "Recent activity (last {n} events): ... {bullet list}"
    """
    events = load_recent_events(n, path)
    if not events:
        return "No prior activity recorded."
    bullets = []
    for e in events:
        loc = f" ({e.slug})" if e.slug else ""
        bullets.append(f"- [{e.event_type}] {e.summary}{loc}")
    return f"Recent activity (last {len(events)} events):\n" + "\n".join(bullets)
