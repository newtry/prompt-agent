"""Tests for storage/library.py — filesystem-backed library."""

from __future__ import annotations

import frontmatter
import pytest

from prompt_agent.storage.library import (
    fork_prompt,
    get_current_version,
    list_prompts,
    list_versions,
    load_prompt,
    save_from_file,
    save_prompt,
    search_prompts,
    set_current_version,
    slugify,
)


def test_slugify() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("  Foo  Bar  ") == "foo-bar"
    assert slugify("a/b\\c") == "a-b-c"
    assert slugify("___") == "unnamed"


def test_save_and_load(tmp_library) -> None:
    saved = save_prompt(
        name="test agent",
        description="a test",
        content="# Role\nYou are X",
        techniques=["CoT"],
        rationale="because",
        assumptions=["a"],
        trade_offs="none",
        tags=["t1"],
    )
    assert saved.slug == "test-agent"
    assert saved.version == 1
    assert saved.path.exists()

    loaded = load_prompt("test-agent")
    assert loaded.content == "# Role\nYou are X"
    assert loaded.metadata["techniques_used"] == ["CoT"]
    assert loaded.metadata["tags"] == ["t1"]


def test_version_increments(tmp_library) -> None:
    save_prompt("agent", "desc", "v1", [], "", [], "")
    save_prompt("agent", "desc", "v2", [], "", [], "")
    assert list_versions("agent") == [1, 2]
    assert get_current_version("agent") == 2


def test_fork_creates_new_prompt(tmp_library) -> None:
    save_prompt("source", "desc", "content", ["CoT"], "r", ["a"], "t", tags=["x"])
    new = fork_prompt("source", "destination")
    assert new.slug == "destination"
    assert new.version == 1
    assert new.content == "content"
    assert list_versions("destination") == [1]


def test_search_by_tag(tmp_library) -> None:
    save_prompt("a", "alpha", "c1", [], "", [], "", tags=["security"])
    save_prompt("b", "beta", "c2", [], "", [], "", tags=["ui"])
    results = search_prompts(tag="security")
    assert len(results) == 1
    assert results[0].slug == "a"


def test_search_by_keyword(tmp_library) -> None:
    save_prompt("foo-bar", "handles auth", "c", [], "", [], "")
    results = search_prompts(keyword="auth")
    assert any(r.slug == "foo-bar" for r in results)


def test_set_current_version(tmp_library) -> None:
    save_prompt("agent", "d", "v1", [], "", [], "")
    save_prompt("agent", "d", "v2", [], "", [], "")
    set_current_version("agent", 1)
    assert get_current_version("agent") == 1


def test_set_invalid_version_raises(tmp_library) -> None:
    save_prompt("agent", "d", "c", [], "", [], "")
    with pytest.raises(FileNotFoundError):
        set_current_version("agent", 99)


def test_save_from_file(tmp_library) -> None:
    md_path = tmp_library.parent / "test.md"
    post = frontmatter.Post("body content")
    post.metadata["name"] = "from file"
    post.metadata["description"] = "imported"
    md_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    saved = save_from_file(md_path)
    assert saved.slug == "from-file"
    assert "body content" in saved.content


def test_list_prompts_empty(tmp_library) -> None:
    assert list_prompts() == []


def test_load_missing_raises(tmp_library) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent")