"""`pa edit` — open a prompt in $EDITOR and save as a new version on change."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import frontmatter
import typer

from prompt_agent.memory import ContextEvent, append_event, ensure_global_dirs
from prompt_agent.storage.library import get_current_version, load_prompt, save_prompt, slugify


def _resolve_editor() -> list[str]:
    """Resolve the editor command from $EDITOR, falling back to platform defaults."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        return shlex.split(editor)
    if os.name == "nt":
        # Try notepad; fall back to write if not available
        for candidate in ("notepad", "code", "vim"):
            if shutil.which(candidate):
                return [candidate]
    for candidate in ("vim", "nano", "vi"):
        if shutil.which(candidate):
            return [candidate]
    raise RuntimeError(
        "No editor found. Set $EDITOR (e.g. export EDITOR='code --wait') or install vim/nano."
    )


def edit(
    target: str = typer.Argument(..., help="Prompt slug (from library)."),
    version: int | None = typer.Option(None, "--version", "-v", help="Edit a specific version (default: current)."),
    editor: str | None = typer.Option(None, "--editor", "-e", help="Override $EDITOR for this invocation."),
) -> None:
    """Open a prompt in your editor. If you save changes, a new version is created."""
    saved = load_prompt(slugify(target), version=version)
    current_version = saved.version

    # Build a temp file with frontmatter + body so the editor sees the metadata too
    post = frontmatter.Post(saved.content)
    post.metadata.update(saved.metadata)
    starting_text = frontmatter.dumps(post)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8", prefix=f"pa-{saved.slug}-v{current_version}-"
    ) as tf:
        tf.write(starting_text)
        tmp_path = Path(tf.name)

    try:
        cmd = shlex.split(editor) if editor else _resolve_editor()
        typer.echo(f"Opening {tmp_path} with: {' '.join(cmd)}")
        result = subprocess.run(cmd + [str(tmp_path)])
        if result.returncode != 0:
            typer.echo(f"warning: editor exited with code {result.returncode}", err=True)

        new_post = frontmatter.load(tmp_path)
        new_content = new_post.content
        if new_content == saved.content and dict(new_post.metadata) == saved.metadata:
            typer.echo("[yellow]No changes detected.[/yellow]")
            return

        # Save as a new version
        new_saved = save_prompt(
            name=saved.metadata.get("name", saved.slug),
            description=saved.metadata.get("description", ""),
            content=new_content,
            techniques=list(saved.metadata.get("techniques_used", [])),
            rationale=saved.metadata.get("rationale", ""),
            assumptions=list(saved.metadata.get("assumptions", [])),
            trade_offs=saved.metadata.get("trade_offs", ""),
            tags=list(saved.metadata.get("tags", [])),
        )
        typer.echo(f"[green]✓[/green] Saved as v{new_saved.version} (was v{current_version})")
        typer.echo(f"  Path: {new_saved.path}")
        # Record to memory.
        try:
            ensure_global_dirs()
            append_event(
                ContextEvent.now(
                    "edit",
                    f"edited '{saved.name}' v{current_version} → v{new_saved.version}",
                    slug=saved.slug,
                    from_version=current_version,
                    to_version=new_saved.version,
                )
            )
        except Exception:
            pass
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass