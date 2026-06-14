"""`pa show` — display a prompt's frontmatter and body."""

from __future__ import annotations

import json

import typer

from prompt_agent.storage.library import load_prompt, slugify


def show(
    target: str = typer.Argument(..., help="Prompt slug (from library) or path to a .md file."),
    version: int | None = typer.Option(None, "--version", "-v", help="Specific version (default: current)."),
    body_only: bool = typer.Option(False, "--body", help="Show only the prompt body, no metadata."),
    meta_only: bool = typer.Option(False, "--meta", help="Show only the metadata."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show a prompt's metadata and content."""
    import frontmatter
    from pathlib import Path

    p = Path(target)
    if p.exists() and p.is_file():
        post = frontmatter.load(p)
        meta = dict(post.metadata)
        content = post.content
        source = f"file:{p}"
        ver = meta.get("version", "?")
    else:
        saved = load_prompt(slugify(target), version=version)
        meta = saved.metadata
        content = saved.content
        source = f"library:{saved.slug}@v{saved.version}"
        ver = saved.version

    if json_output:
        typer.echo(json.dumps({"source": source, "metadata": meta, "body": content}, ensure_ascii=False, indent=2))
        return

    typer.echo(f"[bold]Source:[/bold] {source}")
    if not body_only:
        typer.echo("")
        typer.echo("[bold]Metadata[/bold]")
        for k, v in meta.items():
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False, indent=2)
            typer.echo(f"  [cyan]{k}[/cyan]: {v}")
    if not meta_only:
        typer.echo("")
        typer.echo(f"[bold]Body (v{ver})[/bold]")
        typer.echo("-" * 60)
        typer.echo(content.rstrip())