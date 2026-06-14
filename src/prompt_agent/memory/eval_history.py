"""Eval history — per-run record for regression tracking.

Stored as one JSON file per run at ~/.prompt-agent/evals/<slug>/<run-id>.json.
`pa eval` calls save_eval_run() automatically; `pa eval --baseline N` and
`pa chat` can later call list_eval_runs() to look up past results.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from prompt_agent.evaluators.schema import EvalResult

from .store import GLOBAL_MEMORY_DIR

EVAL_HISTORY_DIR = GLOBAL_MEMORY_DIR / "evals"


def _slug_dir(slug: str) -> Path:
    return EVAL_HISTORY_DIR / slug


@dataclass
class EvalRun:
    run_id: str
    slug: str
    timestamp: str
    agent_model: str
    judge_model: str
    suite_path: str
    baseline_version: int | None = None
    candidate_version: int | None = None
    results: list[dict] = field(default_factory=list)  # serialized EvalResult
    pass_rate: float = 0.0
    avg_score: float = 0.0
    note: str = ""

    @staticmethod
    def from_results(
        slug: str,
        results: list[EvalResult],
        agent_model: str,
        judge_model: str,
        suite_path: str,
        baseline_version: int | None = None,
        candidate_version: int | None = None,
        note: str = "",
    ) -> "EvalRun":
        n = len(results) or 1
        passed = sum(1 for r in results if r.overall_pass)
        return EvalRun(
            run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            + "-"
            + uuid.uuid4().hex[:8],
            slug=slug,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            agent_model=agent_model,
            judge_model=judge_model,
            suite_path=str(suite_path),
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            results=[asdict(r) for r in results],
            pass_rate=passed / n,
            avg_score=sum(r.judge_score for r in results) / n,
            note=note,
        )


def save_eval_run(run: EvalRun) -> Path:
    """Persist a run as JSON. Returns the file path written."""
    d = _slug_dir(run.slug)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{run.run_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(asdict(run), f, ensure_ascii=False, indent=2)
    return path


def list_eval_runs(slug: str) -> list[EvalRun]:
    """List all runs for a slug, newest first."""
    d = _slug_dir(slug)
    if not d.exists():
        return []
    out: list[EvalRun] = []
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            out.append(EvalRun(**data))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def load_eval_run(slug: str, run_id: str) -> EvalRun:
    """Load a specific run by ID. Raises FileNotFoundError if missing."""
    path = _slug_dir(slug) / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Eval run not found: {slug}/{run_id}")
    with path.open("r", encoding="utf-8") as f:
        return EvalRun(**json.load(f))


def latest_eval_run(slug: str) -> EvalRun | None:
    runs = list_eval_runs(slug)
    return runs[0] if runs else None


@dataclass
class EvalComparison:
    slug: str
    a_run_id: str
    b_run_id: str
    a_pass_rate: float
    b_pass_rate: float
    a_avg_score: float
    b_avg_score: float
    improved: list[str] = field(default_factory=list)
    regressed: list[str] = field(default_factory=list)

    @property
    def pass_rate_delta(self) -> float:
        return self.b_pass_rate - self.a_pass_rate

    @property
    def avg_score_delta(self) -> float:
        return self.b_avg_score - self.a_avg_score


def compare_eval_runs(slug: str, a_run_id: str, b_run_id: str) -> EvalComparison:
    a = load_eval_run(slug, a_run_id)
    b = load_eval_run(slug, b_run_id)
    by_a = {r["case_name"]: r for r in a.results}
    by_b = {r["case_name"]: r for r in b.results}
    improved: list[str] = []
    regressed: list[str] = []
    for name in by_a:
        if name in by_b:
            a_pass = by_a[name]["overall_pass"]
            b_pass = by_b[name]["overall_pass"]
            if not a_pass and b_pass:
                improved.append(name)
            elif a_pass and not b_pass:
                regressed.append(name)
    return EvalComparison(
        slug=slug,
        a_run_id=a_run_id,
        b_run_id=b_run_id,
        a_pass_rate=a.pass_rate,
        b_pass_rate=b.pass_rate,
        a_avg_score=a.avg_score,
        b_avg_score=b.avg_score,
        improved=improved,
        regressed=regressed,
    )
