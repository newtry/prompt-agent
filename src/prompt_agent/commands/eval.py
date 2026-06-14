"""`pa eval` — run a test suite against a prompt, optionally comparing to a baseline version."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
import typer

from prompt_agent.core.config import load_config
from prompt_agent.evaluators.llm_judge import LLMJudge, verdict_to_result
from prompt_agent.evaluators.rule import evaluate_rules
from prompt_agent.evaluators.schema import EvalResult, Suite, load_suite
from prompt_agent.memory import (
    ContextEvent,
    EvalRun,
    append_event,
    ensure_global_dirs,
    save_eval_run,
)
from prompt_agent.storage.library import load_prompt


def _resolve_api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or ""


def _run_agent(api_key: str, model: str, system_prompt: str, user_msg: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    return message.content[0].text


def _extract_user_text(test_input: dict) -> str:
    if "user" in test_input:
        return str(test_input["user"])
    if "messages" in test_input and isinstance(test_input["messages"], list):
        for msg in reversed(test_input["messages"]):
            if isinstance(msg, dict) and msg.get("role") == "user":
                return str(msg.get("content", ""))
    return json.dumps(test_input, ensure_ascii=False)


def _run_suite(
    prompt_text: str,
    suite: Suite,
    api_key: str,
    agent_model: str,
    judge_model: str,
    parallel: int,
) -> list[EvalResult]:
    """Run the full eval pipeline for a single prompt against the suite."""
    user_inputs = [_extract_user_text(c.input) for c in suite.cases]
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        agent_outputs = list(
            pool.map(
                lambda inp: _run_agent(api_key, agent_model, prompt_text, inp),
                user_inputs,
            )
        )

    judge = LLMJudge(model=judge_model, api_key=api_key)
    results: list[EvalResult] = []
    for case, output in zip(suite.cases, agent_outputs):
        rule_violations = evaluate_rules(case, output)
        verdict = judge.judge(case, output)
        results.append(verdict_to_result(case, output, verdict, rule_violations))
    return results


def _resolve_target(target: str, version: int | None) -> tuple[str, str, str]:
    """Return (prompt_text, source_label, slug)."""
    p = Path(target)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8"), f"file:{p}", ""
    saved = load_prompt(target, version=version)
    return saved.content, f"library:{saved.slug}@v{saved.version}", saved.slug


def _print_single_table(results: list[EvalResult], source: str) -> None:
    typer.echo(f"Evaluating: {source}")
    name_w = max(len(r.case_name) for r in results) if results else 10
    typer.echo(f"{'CASE'.ljust(name_w)}  {'PASS':<6}  {'SCORE':<6}  VIOLATIONS")
    typer.echo("-" * (name_w + 30))
    for r in results:
        pass_str = (
            typer.style("PASS", fg="green") if r.overall_pass else typer.style("FAIL", fg="red")
        )
        violations = "; ".join(r.rule_violations) if r.rule_violations else "-"
        typer.echo(f"{r.case_name.ljust(name_w)}  {pass_str:<14}  {r.judge_score:<6.2f}  {violations}")
    total = len(results)
    passed = sum(1 for r in results if r.overall_pass)
    typer.echo("")
    typer.echo(f"Summary: {passed}/{total} passed ({100 * passed / total:.0f}%)")


def _print_failures(results: list[EvalResult]) -> None:
    failures = [r for r in results if not r.overall_pass]
    if not failures:
        return
    typer.echo("")
    typer.echo("[bold]Failure details:[/bold]")
    for r in failures:
        typer.echo(f"\n[red]{r.case_name}[/red]")
        typer.echo(f"  Judge: {r.judge_reasoning}")
        if r.rule_violations:
            typer.echo(f"  Rules: {'; '.join(r.rule_violations)}")
        failed_criteria = [k for k, v in r.criteria_results.items() if not v]
        if failed_criteria:
            typer.echo(f"  Failed criteria: {', '.join(failed_criteria)}")


def _record_eval_run(
    slug: str,
    results: list[EvalResult],
    agent_model: str,
    judge_model: str,
    suite_path: Path,
    candidate_version: int | None = None,
    baseline_version: int | None = None,
    note: str = "",
) -> None:
    """Persist a single eval run to memory (best-effort)."""
    try:
        ensure_global_dirs()
        run = EvalRun.from_results(
            slug=slug,
            results=results,
            agent_model=agent_model,
            judge_model=judge_model,
            suite_path=str(suite_path),
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            note=note,
        )
        path = save_eval_run(run)
        n = len(results) or 1
        passed = sum(1 for r in results if r.overall_pass)
        append_event(
            ContextEvent.now(
                "eval",
                f"eval {slug}: {passed}/{n} pass ({run.pass_rate*100:.0f}%)",
                slug=slug,
                run_id=run.run_id,
                pass_rate=run.pass_rate,
            )
        )
        typer.echo(f"\n[dim]Saved eval run: {path.name}[/dim]")
    except Exception as e:  # noqa: BLE001 — memory is best-effort
        typer.echo(f"\n[yellow]warning:[/yellow] could not save eval run: {e}", err=True)


def _print_comparison(
    baseline: list[EvalResult],
    candidate: list[EvalResult],
    baseline_label: str,
    candidate_label: str,
) -> None:
    by_name_b = {r.case_name: r for r in baseline}
    by_name_c = {r.case_name: r for r in candidate}

    # Align by case name (assumes same suite)
    common_names = [n for n in by_name_b if n in by_name_c]
    name_w = max((len(n) for n in common_names), default=10)
    typer.echo(f"Comparing: [cyan]{baseline_label}[/cyan] vs [cyan]{candidate_label}[/cyan]")
    typer.echo(f"{'CASE'.ljust(name_w)}  {'BASELINE':<9}  {'CANDIDATE':<10}  DELTA")
    typer.echo("-" * (name_w + 40))

    improved: list[str] = []
    regressed: list[str] = []

    for name in common_names:
        b = by_name_b[name]
        c = by_name_c[name]
        b_str = (
            typer.style("PASS", fg="green") if b.overall_pass else typer.style("FAIL", fg="red")
        )
        c_str = (
            typer.style("PASS", fg="green") if c.overall_pass else typer.style("FAIL", fg="red")
        )
        if not b.overall_pass and c.overall_pass:
            delta = typer.style("IMPROVED", fg="green", bold=True)
            improved.append(name)
        elif b.overall_pass and not c.overall_pass:
            delta = typer.style("REGRESSED", fg="red", bold=True)
            regressed.append(name)
        elif c.judge_score > b.judge_score + 0.01:
            delta = typer.style(f"+{c.judge_score - b.judge_score:.2f}", fg="green")
        elif c.judge_score < b.judge_score - 0.01:
            delta = typer.style(f"{c.judge_score - b.judge_score:.2f}", fg="red")
        else:
            delta = "="
        typer.echo(f"{name.ljust(name_w)}  {b_str:<17}  {c_str:<18}  {delta}")

    # Score summaries
    b_pass = sum(1 for r in baseline if r.overall_pass)
    c_pass = sum(1 for r in candidate if r.overall_pass)
    b_score = sum(r.judge_score for r in baseline) / max(len(baseline), 1)
    c_score = sum(r.judge_score for r in candidate) / max(len(candidate), 1)
    typer.echo("")
    typer.echo(f"Baseline:   {b_pass}/{len(baseline)} pass  |  avg score: {b_score:.2f}")
    typer.echo(f"Candidate:  {c_pass}/{len(candidate)} pass  |  avg score: {c_score:.2f}")
    typer.echo(
        f"Delta:      {c_pass - b_pass:+d} pass  |  score {c_score - b_score:+.2f}"
    )
    if improved:
        typer.echo(f"\n[green]Improved ({len(improved)}):[/green] {', '.join(improved)}")
    if regressed:
        typer.echo(f"\n[red]Regressed ({len(regressed)}):[/red] {', '.join(regressed)}")
        typer.echo("\nRegression details:")
        for name in regressed:
            c = by_name_c[name]
            typer.echo(f"  [red]{name}[/red]: {c.judge_reasoning}")


def eval(
    target: str = typer.Argument(..., help="Prompt slug (from library) or path to a .md file."),
    suite: Path = typer.Option(..., "--suite", "-s", help="Path to a YAML test suite."),
    baseline: int | None = typer.Option(
        None,
        "--baseline",
        "-b",
        help="Compare against this version of the same prompt (requires target to be a slug).",
    ),
    version: int | None = typer.Option(None, "--version", "-v", help="Version to evaluate as the candidate (default: current)."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the agent model."),
    judge_model: str | None = typer.Option(None, "--judge-model", "-j", help="Override the judge model."),
) -> None:
    """Run a test suite against a prompt and report pass/fail per case.

    With --baseline N, compare the candidate version against version N of the same slug.
    """
    cfg = load_config()
    agent_model = model or cfg.llm.default_model
    judge_model = judge_model or cfg.llm.judge_model

    candidate_text, candidate_label, slug = _resolve_target(target, version)
    if baseline is not None and not slug:
        typer.echo("error: --baseline requires target to be a slug, not a file", err=True)
        raise typer.Exit(code=1)

    try:
        s = load_suite(suite)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    api_key = _resolve_api_key()
    if not api_key:
        typer.echo("error: no API key (set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN)", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Running {len(s.cases)} case(s)")
    typer.echo(f"  Agent model: {agent_model}  |  Judge model: {judge_model}")
    typer.echo("")

    candidate_results = _run_suite(
        prompt_text=candidate_text,
        suite=s,
        api_key=api_key,
        agent_model=agent_model,
        judge_model=judge_model,
        parallel=cfg.eval.parallel,
    )

    if baseline is None:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "source": candidate_label,
                        "agent_model": agent_model,
                        "judge_model": judge_model,
                        "results": [r.__dict__ for r in candidate_results],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        _print_single_table(candidate_results, candidate_label)
        _print_failures(candidate_results)
        if slug:
            _record_eval_run(
                slug=slug,
                results=candidate_results,
                agent_model=agent_model,
                judge_model=judge_model,
                suite_path=suite,
                candidate_version=version,
            )
        return

    # Comparison mode
    try:
        baseline_saved = load_prompt(slug, version=baseline)
    except FileNotFoundError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)
    baseline_text = baseline_saved.content
    baseline_label = f"library:{slug}@v{baseline_saved.version}"

    baseline_results = _run_suite(
        prompt_text=baseline_text,
        suite=s,
        api_key=api_key,
        agent_model=agent_model,
        judge_model=judge_model,
        parallel=cfg.eval.parallel,
    )

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "baseline": {
                        "source": baseline_label,
                        "results": [r.__dict__ for r in baseline_results],
                    },
                    "candidate": {
                        "source": candidate_label,
                        "results": [r.__dict__ for r in candidate_results],
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    _print_comparison(baseline_results, candidate_results, baseline_label, candidate_label)
    if slug:
        _record_eval_run(
            slug=slug,
            results=baseline_results,
            agent_model=agent_model,
            judge_model=judge_model,
            suite_path=suite,
            candidate_version=baseline_saved.version,
            note="auto-recorded from --baseline eval",
        )
        _record_eval_run(
            slug=slug,
            results=candidate_results,
            agent_model=agent_model,
            judge_model=judge_model,
            suite_path=suite,
            candidate_version=version,
            baseline_version=baseline_saved.version,
            note=f"compared against v{baseline_saved.version}",
        )