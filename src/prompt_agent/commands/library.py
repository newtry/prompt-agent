"""`pa library` — manage the local prompt library."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import frontmatter
import typer

from prompt_agent.memory import ContextEvent, append_event, ensure_global_dirs
from prompt_agent.storage.library import (
    fork_prompt,
    list_prompts,
    load_prompt,
    save_from_file,
    search_prompts,
    slugify,
)

library_app = typer.Typer(help="Manage the local prompt library.", no_args_is_help=True)
seed_app = typer.Typer(help="Manage built-in seed prompts.", no_args_is_help=True)
library_app.add_typer(seed_app, name="seed")


@library_app.command("list")
def list_cmd(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by keyword (matches name/description/slug/tags)."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List all prompts in the library."""
    if tag or search:
        prompts = search_prompts(tag=tag, keyword=search)
    else:
        prompts = list_prompts()

    if json_output:
        typer.echo(
            json.dumps(
                [
                    {
                        "slug": p.slug,
                        "name": p.name,
                        "description": p.description,
                        "current_version": p.current_version,
                        "latest_version": p.latest_version,
                        "tags": p.tags,
                    }
                    for p in prompts
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not prompts:
        typer.echo("[yellow]Library is empty.[/yellow] Use `pa new \"...\"` to add prompts.")
        return

    slug_w = max(len(p.slug) for p in prompts)
    typer.echo(f"{'SLUG'.ljust(slug_w)}  {'CUR':<4}  {'LAT':<4}  TAGS         NAME")
    typer.echo("-" * (slug_w + 50))
    for p in prompts:
        tags_str = ",".join(p.tags) if p.tags else "-"
        typer.echo(
            f"{p.slug.ljust(slug_w)}  v{p.current_version:<3}  v{p.latest_version:<3}  {tags_str.ljust(12)} {p.name}"
        )


@library_app.command("show")
def show_cmd(
    slug: str = typer.Argument(..., help="Prompt slug."),
    version: int | None = typer.Option(None, "--version", "-v", help="Specific version (default: current)."),
) -> None:
    """Show a prompt (delegates to pa show)."""
    saved = load_prompt(slug, version=version)
    typer.echo(f"[bold]library:{saved.slug}@v{saved.version}[/bold]")
    typer.echo(f"[bold]Description:[/bold] {saved.metadata.get('description', '')}")
    typer.echo(f"[bold]Tags:[/bold] {', '.join(saved.metadata.get('tags', [])) or '-'}")
    typer.echo("")
    typer.echo(saved.content.rstrip())


@library_app.command("fork")
def fork_cmd(
    slug: str = typer.Argument(..., help="Source prompt slug to fork."),
    name: str = typer.Option(..., "--name", "-n", help="Name for the new forked prompt."),
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Tags to add (repeatable)."),
) -> None:
    """Copy the current version of a prompt into a new one."""
    try:
        new_saved = fork_prompt(slugify(slug), name)
    except FileNotFoundError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)
    # Apply tags override if provided
    if tag:
        from prompt_agent.storage.library import _read_meta, _write_meta  # noqa: PLC0415

        meta = _read_meta(new_saved.slug)
        meta["tags"] = tag
        _write_meta(new_saved.slug, meta)
    typer.echo(f"[green]✓[/green] Forked {slug} → {new_saved.slug} (v{new_saved.version})")
    typer.echo(f"  Path: {new_saved.path}")
    try:
        ensure_global_dirs()
        append_event(
            ContextEvent.now(
                "fork",
                f"forked {slug} → {new_saved.slug}",
                slug=new_saved.slug,
                source=slug,
            )
        )
    except Exception:
        pass


@library_app.command("save")
def save_cmd(
    file: Path = typer.Argument(..., help="Path to a .md prompt file to import."),
    name: str | None = typer.Option(None, "--name", "-n", help="Override the prompt name."),
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Tags to add (repeatable)."),
) -> None:
    """Import an existing .md prompt file into the library."""
    if not file.exists():
        typer.echo(f"error: file not found: {file}", err=True)
        raise typer.Exit(code=1)
    saved = save_from_file(file, name=name, tags=tag)
    typer.echo(f"[green]✓[/green] Imported: {saved.path}")
    typer.echo(f"  Slug: {saved.slug}  |  Version: v{saved.version}")
    try:
        ensure_global_dirs()
        append_event(
            ContextEvent.now(
                "save",
                f"imported '{saved.name}' from {file.name}",
                slug=saved.slug,
                source_path=str(file),
            )
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Seed subcommands
# ---------------------------------------------------------------------------


def _seed_root():
    return resources.files("prompt_agent.seed")


def _list_seed_names() -> list[str]:
    root = _seed_root()
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(("_", "."))
    )


def _load_seed(name: str) -> tuple[str, str | None]:
    """Return (prompt_md_text, suite_yaml_text_or_none)."""
    root = _seed_root()
    seed_dir = root / name
    md = (seed_dir / "v1.md").read_text(encoding="utf-8")
    suite_path = seed_dir / "suite.yaml"
    suite = suite_path.read_text(encoding="utf-8") if suite_path.exists() else None
    return md, suite


def _seed_describe(name: str) -> dict:
    md, _ = _load_seed(name)
    post = frontmatter.loads(md)
    return {
        "name": name,
        "title": post.metadata.get("name", name),
        "description": post.metadata.get("description", ""),
        "tags": post.metadata.get("tags", []),
        "techniques": post.metadata.get("techniques_used", []),
    }


@seed_app.command("list")
def seed_list_cmd() -> None:
    """List available seed prompts."""
    names = _list_seed_names()
    if not names:
        typer.echo("[yellow]No seeds bundled.[/yellow]")
        return
    name_w = max(len(n) for n in names)
    typer.echo(f"{'NAME'.ljust(name_w)}  TAGS                  DESCRIPTION")
    typer.echo("-" * (name_w + 60))
    for n in names:
        info = _seed_describe(n)
        tags = ",".join(info["tags"]) if info["tags"] else "-"
        typer.echo(f"{n.ljust(name_w)}  {tags.ljust(20)} {info['description']}")


@seed_app.command("show")
def seed_show_cmd(
    name: str = typer.Argument(..., help="Seed name (e.g. react-coder)."),
    body_only: bool = typer.Option(False, "--body", help="Show only the prompt body."),
) -> None:
    """Show a seed prompt's contents."""
    try:
        md, _ = _load_seed(name)
    except (FileNotFoundError, ModuleNotFoundError):
        typer.echo(f"error: seed '{name}' not found", err=True)
        raise typer.Exit(code=1)
    post = frontmatter.loads(md)
    if not body_only:
        typer.echo(f"[bold]seed:{name}[/bold]")
        for k, v in post.metadata.items():
            typer.echo(f"  [cyan]{k}[/cyan]: {v}")
        typer.echo("")
    typer.echo(post.content.rstrip())


@seed_app.command("install")
def seed_install_cmd(
    name: list[str] | None = typer.Argument(None, help="Seed name(s) to install. Omit to install all."),
    all_seeds: bool = typer.Option(False, "--all", help="Install all available seeds."),
) -> None:
    """Install seed prompts into the local library."""
    if all_seeds or not name:
        targets = _list_seed_names()
    else:
        targets = name

    installed = 0
    for n in targets:
        try:
            md, _ = _load_seed(n)
        except (FileNotFoundError, ModuleNotFoundError):
            typer.echo(f"[yellow]skip[/yellow] {n}: not found")
            continue
        # Write to a temp file then import via save_from_file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tf:
            tf.write(md)
            tmp = Path(tf.name)
        try:
            saved = save_from_file(tmp, name=None)
            typer.echo(f"[green]✓[/green] {n} -> {saved.slug} v{saved.version}")
            installed += 1
            try:
                ensure_global_dirs()
                append_event(
                    ContextEvent.now(
                        "seed_install",
                        f"installed seed '{n}'",
                        slug=saved.slug,
                        seed=n,
                    )
                )
            except Exception:
                pass
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    typer.echo(f"\nInstalled {installed} seed(s). Run `pa library list` to see them.")