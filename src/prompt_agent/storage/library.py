"""Filesystem-backed prompt library.

Layout:
    ~/.prompt-agent/library/
        <slug>/
            v1.md
            v2.md
            meta.toml      # name, description, current_version, tags, created, updated
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter

from prompt_agent.core.config import ensure_global_dirs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w  # write-only TOML serializer

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or "unnamed"


@dataclass
class SavedPrompt:
    slug: str
    path: Path
    version: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptInfo:
    """Lightweight metadata about a prompt in the library."""
    slug: str
    name: str
    description: str
    current_version: int
    latest_version: int
    tags: list[str]
    path: Path


def _library_root() -> Path:
    return ensure_global_dirs() / "library"


def _prompt_dir(slug: str) -> Path:
    return _library_root() / slug


def _meta_path(slug: str) -> Path:
    return _prompt_dir(slug) / "meta.toml"


def _read_meta(slug: str) -> dict[str, Any]:
    p = _meta_path(slug)
    if not p.exists():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def _write_meta(slug: str, data: dict[str, Any]) -> None:
    p = _meta_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        tomli_w.dump(data, f)


def _list_existing_versions(slug: str) -> list[int]:
    d = _prompt_dir(slug)
    if not d.exists():
        return []
    return sorted(
        int(p.stem.lstrip("v"))
        for p in d.glob("v*.md")
        if p.stem.lstrip("v").isdigit()
    )


def _next_version(slug: str) -> int:
    existing = _list_existing_versions(slug)
    return (max(existing) if existing else 0) + 1


def save_prompt(
    name: str,
    description: str,
    content: str,
    techniques: list[str],
    rationale: str,
    assumptions: list[str],
    trade_offs: str,
    tags: list[str] | None = None,
) -> SavedPrompt:
    """Save a new prompt version. Updates meta index with new current_version."""
    slug = slugify(name)
    version = _next_version(slug)
    d = _prompt_dir(slug)
    d.mkdir(parents=True, exist_ok=True)

    today = str(date.today())
    meta = _read_meta(slug)
    if not meta:
        meta = {
            "name": name,
            "description": description,
            "created": today,
            "tags": tags or [],
        }
    meta["current_version"] = version
    meta["updated"] = today

    post = frontmatter.Post(content)
    post.metadata["name"] = name
    post.metadata["description"] = description
    post.metadata["version"] = version
    post.metadata["tags"] = tags or []
    post.metadata["techniques_used"] = techniques
    post.metadata["rationale"] = rationale
    post.metadata["assumptions"] = assumptions
    post.metadata["trade_offs"] = trade_offs
    post.metadata["created"] = today

    path = d / f"v{version}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    _write_meta(slug, meta)

    return SavedPrompt(slug=slug, path=path, version=version, content=content, metadata=post.metadata)


def load_prompt(slug: str, version: int | None = None) -> SavedPrompt:
    """Load a prompt. If version is None, use meta.toml's current_version."""
    d = _prompt_dir(slug)
    if not d.exists():
        raise FileNotFoundError(f"Prompt '{slug}' not found in library")

    if version is None:
        meta = _read_meta(slug)
        version = meta.get("current_version")
        if version is None:
            versions = _list_existing_versions(slug)
            if not versions:
                raise FileNotFoundError(f"No versions found for prompt '{slug}'")
            version = versions[-1]

    path = d / f"v{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{slug}' version {version} not found")
    post = frontmatter.load(path)
    return SavedPrompt(
        slug=slug,
        path=path,
        version=int(version),
        content=post.content,
        metadata=dict(post.metadata),
    )


def get_current_version(slug: str) -> int:
    """Get the version marked as current in meta.toml. Falls back to latest v*.md."""
    meta = _read_meta(slug)
    if "current_version" in meta:
        return int(meta["current_version"])
    versions = _list_existing_versions(slug)
    if not versions:
        raise FileNotFoundError(f"No versions found for prompt '{slug}'")
    return versions[-1]


def list_versions(slug: str) -> list[int]:
    """List all versions of a prompt, sorted ascending."""
    return _list_existing_versions(slug)


def list_prompts() -> list[PromptInfo]:
    """List all prompts in the library with their metadata."""
    root = _library_root()
    if not root.exists():
        return []
    infos: list[PromptInfo] = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        slug = p.name
        meta = _read_meta(slug)
        versions = _list_existing_versions(slug)
        if not versions:
            continue
        infos.append(
            PromptInfo(
                slug=slug,
                name=meta.get("name", slug),
                description=meta.get("description", ""),
                current_version=int(meta.get("current_version", versions[-1])),
                latest_version=versions[-1],
                tags=list(meta.get("tags", [])),
                path=p,
            )
        )
    return infos


def search_prompts(tag: str | None = None, keyword: str | None = None) -> list[PromptInfo]:
    """Filter the library by tag and/or keyword (matches name/description/slug/tags)."""
    results = list_prompts()
    if tag:
        results = [i for i in results if tag in i.tags]
    if keyword:
        kw = keyword.lower()
        results = [
            i for i in results
            if kw in i.slug.lower()
            or kw in i.name.lower()
            or kw in i.description.lower()
            or any(kw in t.lower() for t in i.tags)
        ]
    return results


def fork_prompt(source_slug: str, new_name: str) -> SavedPrompt:
    """Copy the current version of source_slug into a new prompt with new_name."""
    source = load_prompt(source_slug)  # loads current
    return save_prompt(
        name=new_name,
        description=source.metadata.get("description", ""),
        content=source.content,
        techniques=list(source.metadata.get("techniques_used", [])),
        rationale=source.metadata.get("rationale", ""),
        assumptions=list(source.metadata.get("assumptions", [])),
        trade_offs=source.metadata.get("trade_offs", ""),
        tags=list(source.metadata.get("tags", [])),
    )


def save_from_file(path: Path, name: str | None = None, tags: list[str] | None = None) -> SavedPrompt:
    """Import an existing .md prompt file (with optional frontmatter) into the library."""
    import frontmatter

    post = frontmatter.load(path)
    name = name or post.metadata.get("name") or path.stem
    description = post.metadata.get("description", "")
    return save_prompt(
        name=name,
        description=description,
        content=post.content,
        techniques=list(post.metadata.get("techniques_used", [])),
        rationale=post.metadata.get("rationale", ""),
        assumptions=list(post.metadata.get("assumptions", [])),
        trade_offs=post.metadata.get("trade_offs", ""),
        tags=tags if tags is not None else list(post.metadata.get("tags", [])),
    )


def set_current_version(slug: str, version: int) -> None:
    """Update meta.toml's current_version pointer."""
    versions = _list_existing_versions(slug)
    if version not in versions:
        raise FileNotFoundError(f"Prompt '{slug}' has no version {version}")
    meta = _read_meta(slug)
    meta["current_version"] = version
    from datetime import date as _date

    meta["updated"] = str(_date.today())
    _write_meta(slug, meta)