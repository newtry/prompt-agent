"""Typer CLI entry point for PromptAgent."""

from __future__ import annotations

import sys

import typer

from prompt_agent.commands.diagnose import diagnose as diagnose_cmd
from prompt_agent.commands.edit import edit as edit_cmd
from prompt_agent.commands.eval import eval as eval_cmd
from prompt_agent.commands.library import library_app
from prompt_agent.commands.new import new as new_cmd
from prompt_agent.commands.show import show as show_cmd

# Force UTF-8 stdout on Windows so Unicode glyphs (✓ ✗ etc.) don't break GBK terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

app = typer.Typer(
    name="pa",
    help="PromptAgent — CLI for designing, testing, and managing agent system prompts.",
    no_args_is_help=True,
    add_completion=False,
)

app.command(name="new", help="Generate a new system prompt from a description.")(new_cmd)
app.command(name="show", help="Display a prompt's metadata and body.")(show_cmd)
app.command(name="edit", help="Open a prompt in $EDITOR; saves as a new version on change.")(edit_cmd)
app.command(name="diagnose", help="Analyze an existing prompt and suggest fixes.")(diagnose_cmd)
app.command(name="eval", help="Run a test suite against a prompt and report results.")(eval_cmd)
app.add_typer(library_app, name="library")


@app.command(name="version")
def version_cmd(
    slug: str = typer.Argument(None, help="Prompt slug (omit to show pa version)."),
    list_versions_flag: bool = typer.Option(False, "--list", "-l", help="List all versions of the prompt."),
    diff: str | None = typer.Option(None, "--diff", help="Diff two versions, e.g. 'v1..v2' or '1..2'."),
    set_version: int | None = typer.Option(None, "--set", help="Set the current version pointer."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Without args: show pa version. With slug: manage prompt versions."""
    if slug is None:
        from prompt_agent import __version__

        typer.echo(f"pa {__version__}")
        return
    # Delegate to the version module's logic
    from prompt_agent.commands.version import run as version_run

    version_run(
        slug=slug,
        list_versions_flag=list_versions_flag,
        diff=diff,
        set_version=set_version,
        json_output=json_output,
    )


if __name__ == "__main__":
    app()