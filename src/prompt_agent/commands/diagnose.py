"""`pa diagnose` — analyze an existing prompt and suggest fixes."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from prompt_agent.core.client import PromptClient, PromptGenerationError
from prompt_agent.core.config import load_config
from prompt_agent.storage.library import load_prompt, slugify


_SEVERITY_STYLE = {
    "high": typer.style("HIGH", fg="red", bold=True),
    "medium": typer.style("MED", fg="yellow", bold=True),
    "low": typer.style("LOW", fg="cyan"),
}


def _resolve_prompt_source(target: str) -> tuple[str, str]:
    """Return (prompt_text, source_label) for either a slug or a file path."""
    p = Path(target)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8"), f"file:{p}"
    # Treat as library slug
    saved = load_prompt(slugify(target))
    return saved.content, f"library:{saved.slug}@v{saved.version}"


def diagnose(
    target: str = typer.Argument(..., help="Prompt slug (from library) or path to a .md file."),
    case: Path | None = typer.Option(None, "--case", "-c", help="Path to a failure case file (JSON or YAML)."),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON instead of human-readable report."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the default LLM model."),
) -> None:
    """Diagnose an existing prompt and suggest improvements."""
    try:
        prompt_text, source = _resolve_prompt_source(target)
    except FileNotFoundError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    failure_case_str: str | None = None
    if case is not None:
        if not case.exists():
            typer.echo(f"error: case file not found: {case}", err=True)
            raise typer.Exit(code=1)
        from prompt_agent.core.client import _read_failure_case

        failure_case_str = _read_failure_case(case)

    cfg = load_config()
    try:
        client = PromptClient(model=model or cfg.llm.default_model)
    except PromptGenerationError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    try:
        report = client.diagnose(prompt_text, failure_case_str)
    except PromptGenerationError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "source": source,
                    "summary": report.summary,
                    "issues": [i.__dict__ for i in report.issues],
                    "root_cause_analysis": report.root_cause_analysis,
                    "suggested_rewrite": report.suggested_rewrite,
                    "checklist_results": report.checklist_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(f"[bold]Diagnose:[/bold] {source}")
    typer.echo(f"[bold]Summary:[/bold] {report.summary}")
    typer.echo("")

    if not report.issues:
        typer.echo("[green]No issues found.[/green]")
    else:
        for idx, issue in enumerate(report.issues, 1):
            sev = _SEVERITY_STYLE.get(issue.severity.lower(), issue.severity.upper())
            typer.echo(f"[{sev}] #{idx} [{issue.category}] @ {issue.location}")
            typer.echo(f"  Problem:  {issue.problem}")
            typer.echo(f"  Fix:      {issue.fix}")
            if issue.replacement:
                typer.echo(f"  Replace:  [italic]{issue.replacement}[/italic]")
            typer.echo("")

    if report.root_cause_analysis:
        typer.echo(f"[bold]Root cause:[/bold] {report.root_cause_analysis}")
        typer.echo("")

    failed = [k for k, v in report.checklist_results.items() if v.startswith("fail")]
    if failed:
        typer.echo(f"[red]Checklist failures:[/red] {', '.join(failed)}")
        typer.echo("")

    if report.suggested_rewrite:
        typer.echo("[bold]Suggested rewrite available.[/bold] Run with --json to extract.")