"""`pa version <slug>` — view, compare, and switch prompt versions."""

from __future__ import annotations

import difflib
import json

import typer

from prompt_agent.storage.library import (
    get_current_version,
    list_versions,
    load_prompt,
    set_current_version,
)


def run(
    slug: str,
    list_versions_flag: bool = False,
    diff: str | None = None,
    set_version: int | None = None,
    json_output: bool = False,
) -> None:
    if list_versions_flag:
        versions = list_versions(slug)
        current = get_current_version(slug)
        if json_output:
            typer.echo(json.dumps({"slug": slug, "versions": versions, "current": current}))
            return
        for v in versions:
            marker = "*" if v == current else " "
            typer.echo(f"  {marker} v{v}")
        return

    if diff is not None:
        if ".." not in diff:
            typer.echo("error: --diff must be in format 'v1..v2' or '1..2'", err=True)
            raise typer.Exit(code=1)
        left_s, right_s = diff.split("..", 1)
        left_v = int(left_s.lstrip("v"))
        right_v = int(right_s.lstrip("v"))
        left = load_prompt(slug, version=left_v)
        right = load_prompt(slug, version=right_v)
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "left": {"version": left.version, "content": left.content},
                        "right": {"version": right.version, "content": right.content},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        diff_lines = difflib.unified_diff(
            left.content.splitlines(keepends=True),
            right.content.splitlines(keepends=True),
            fromfile=f"v{left.version}",
            tofile=f"v{right.version}",
        )
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                typer.echo(typer.style(line.rstrip(), fg="green"))
            elif line.startswith("-") and not line.startswith("---"):
                typer.echo(typer.style(line.rstrip(), fg="red"))
            elif line.startswith("@"):
                typer.echo(typer.style(line.rstrip(), fg="cyan"))
            else:
                typer.echo(line.rstrip())
        return

    if set_version is not None:
        try:
            set_current_version(slug, set_version)
        except FileNotFoundError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"[green]✓[/green] {slug} current_version = v{set_version}")
        return

    # Default: show current version info
    try:
        current = get_current_version(slug)
        saved = load_prompt(slug, version=current)
    except FileNotFoundError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)
    versions = list_versions(slug)
    typer.echo(f"[bold]{slug}[/bold] — current: v{current}  |  total versions: {len(versions)}")
    typer.echo(f"  Created: {saved.metadata.get('created', '-')}")
    typer.echo("")
    typer.echo("Usage:")
    typer.echo(f"  pa show {slug}                  # show current")
    typer.echo(f"  pa version {slug} --list        # list versions")
    typer.echo(f"  pa version {slug} --diff 1..2   # diff two versions")
    typer.echo(f"  pa version {slug} --set 2       # switch current")