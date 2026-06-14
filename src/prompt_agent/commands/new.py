"""`pa new` — generate a new system prompt from a description."""

from __future__ import annotations

import json
import sys

import typer

from prompt_agent.core.client import PromptClient, PromptGenerationError
from prompt_agent.core.config import load_config
from prompt_agent.memory import ContextEvent, append_event, ensure_global_dirs
from prompt_agent.storage.library import save_prompt


def new(
    description: str = typer.Argument(..., help="Natural-language description of the agent to design."),
    name: str | None = typer.Option(None, "--name", "-n", help="Name for the prompt (defaults to slugified description)."),
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Tags for organization (repeatable)."),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON instead of human-readable summary."),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the default LLM model."),
) -> None:
    """Generate a new system prompt from a description and save it to the library."""
    cfg = load_config()
    try:
        client = PromptClient(model=model or cfg.llm.default_model)
    except PromptGenerationError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    try:
        result = client.generate(description)
    except PromptGenerationError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    # Derive a default name from description if not provided
    if name is None:
        name = description[:40].strip()
        if len(description) > 40:
            name = name.rsplit(" ", 1)[0]  # Trim to last word boundary

    saved = save_prompt(
        name=name,
        description=description,
        content=result.prompt,
        techniques=result.techniques_used,
        rationale=result.rationale,
        assumptions=result.assumptions,
        trade_offs=result.trade_offs,
        tags=tag,
    )

    # Record to memory (best-effort: don't fail the command on memory errors).
    try:
        ensure_global_dirs()
        append_event(
            ContextEvent.now(
                "new",
                f"generated '{saved.name}' v{saved.version} — {description[:60]}",
                slug=saved.slug,
                techniques=result.techniques_used,
            )
        )
    except Exception:
        pass

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "slug": saved.slug,
                    "version": saved.version,
                    "path": str(saved.path),
                    "prompt": result.prompt,
                    "rationale": result.rationale,
                    "techniques_used": result.techniques_used,
                    "assumptions": result.assumptions,
                    "trade_offs": result.trade_offs,
                    "checklist_results": result.checklist_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    typer.echo(f"[green]✓[/green] Saved: {saved.path}")
    typer.echo(f"  Slug: {saved.slug}  |  Version: v{saved.version}")
    typer.echo(f"  Techniques: {', '.join(result.techniques_used) or '(none)'}")
    if result.assumptions:
        typer.echo(f"  [yellow]Assumptions[/yellow]: {len(result.assumptions)} item(s) — review before use")
        for a in result.assumptions:
            typer.echo(f"    - {a}")
    failed = [k for k, v in result.checklist_results.items() if v.startswith("fail")]
    if failed:
        typer.echo(f"  [red]Checklist failures[/red]: {', '.join(failed)}")
    typer.echo("")
    typer.echo("Tip: review with `pa show <slug>` or edit with `pa edit <slug>`")