"""`pa chat` — interactive REPL for prompt engineering.

The REPL maintains a multi-turn conversation with the LLM. The system prompt
includes the user's preferences and recent activity (from memory), plus a
description of available actions. The LLM responds with either natural
language or a JSON action block that the REPL dispatches to the underlying
CLI commands.

This is intentionally a thin conversational layer over the existing
commands — it does not duplicate any business logic.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import typer

from prompt_agent.core.client import PromptClient, PromptGenerationError
from prompt_agent.core.config import load_config
from prompt_agent.evaluators.schema import load_suite
from prompt_agent.memory import (
    ContextEvent,
    MemoryStore,
    Preferences,
    append_event,
    ensure_global_dirs,
    list_eval_runs,
    load_preferences,
    summarize_recent,
)
from prompt_agent.storage.library import (
    fork_prompt,
    list_prompts,
    load_prompt,
    save_prompt,
    save_from_file,
    search_prompts,
    slugify,
)

chat_app = typer.Typer(help="Interactive REPL for prompt engineering.", no_args_is_help=False)


# ---------------------------------------------------------------------------
# Action protocol
# ---------------------------------------------------------------------------

_ACTION_RE = re.compile(r"```pa-action\s*\n(.*?)\n```", re.DOTALL)


@dataclass
class Action:
    """A parsed action emitted by the LLM."""

    name: str
    args: dict = field(default_factory=dict)
    rationale: str = ""


def _parse_action(text: str) -> Action | None:
    """Look for a ```pa-action ...``` block. If found, return the parsed action.

    Tolerates extra prose around the block — only the first ```pa-action
    block is honored.
    """
    m = _ACTION_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "action" not in data:
        return None
    return Action(
        name=str(data["action"]),
        args={k: v for k, v in data.items() if k not in ("action", "rationale")},
        rationale=str(data.get("rationale", "")),
    )


def _strip_action_block(text: str) -> str:
    """Remove the action block from text so we can print the prose only."""
    return _ACTION_RE.sub("", text).rstrip()


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------

# Each handler receives (args, ctx) and returns a textual result for the user
# (printed by the REPL) and a dict for the LLM (appended to the conversation
# so the LLM knows what happened).

def _action_show(args: dict) -> tuple[str, dict]:
    slug = args.get("slug")
    if not slug:
        return "show: missing 'slug'", {"error": "missing slug"}
    version = args.get("version")
    try:
        saved = load_prompt(slug, version=version)
    except FileNotFoundError as e:
        return f"show: {e}", {"error": str(e)}
    out = (
        f"[{saved.slug} v{saved.version}]\n"
        f"  {saved.metadata.get('description', '')}\n"
        f"  tags: {', '.join(saved.metadata.get('tags', [])) or '-'}\n\n"
        f"{saved.content}"
    )
    return out, {"slug": saved.slug, "version": saved.version, "content": saved.content}


def _action_list(args: dict) -> tuple[str, dict]:
    prompts = list_prompts()
    if args.get("tag") or args.get("keyword"):
        prompts = search_prompts(tag=args.get("tag"), keyword=args.get("keyword"))
    rows = [
        {
            "slug": p.slug,
            "name": p.name,
            "version": p.current_version,
            "tags": p.tags,
        }
        for p in prompts
    ]
    table = "\n".join(
        f"  {r['slug']:<24}  v{r['version']}  {', '.join(r['tags']) or '-'}"
        for r in rows
    ) or "  (empty)"
    return f"Library ({len(rows)} prompt(s)):\n{table}", {"count": len(rows), "prompts": rows}


def _action_eval(args: dict, ctx: "ChatContext") -> tuple[str, dict]:
    slug = args.get("slug")
    suite_path = args.get("suite")
    if not slug or not suite_path:
        return "eval: need 'slug' and 'suite'", {"error": "missing args"}
    try:
        saved = load_prompt(slug)
    except FileNotFoundError as e:
        return f"eval: {e}", {"error": str(e)}
    suite_p = Path(suite_path)
    try:
        s = load_suite(suite_p)
    except (FileNotFoundError, ValueError) as e:
        return f"eval: {e}", {"error": str(e)}
    cfg = load_config()
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    if not api_key:
        return "eval: no API key set", {"error": "no API key"}

    from prompt_agent.commands.eval import _run_suite
    results = _run_suite(
        prompt_text=saved.content,
        suite=s,
        api_key=api_key,
        agent_model=cfg.llm.default_model,
        judge_model=cfg.llm.judge_model,
        parallel=cfg.eval.parallel,
    )
    n = len(results) or 1
    passed = sum(1 for r in results if r.overall_pass)
    table = "\n".join(
        f"  {'PASS' if r.overall_pass else 'FAIL'}  {r.judge_score:.2f}  {r.case_name}"
        for r in results
    )
    summary = (
        f"Eval {slug} v{saved.version} — {passed}/{n} pass ({100*passed/n:.0f}%)\n{table}"
    )
    # Best-effort: persist as eval run
    try:
        from prompt_agent.memory import EvalRun, save_eval_run
        run = EvalRun.from_results(
            slug=slug,
            results=results,
            agent_model=cfg.llm.default_model,
            judge_model=cfg.llm.judge_model,
            suite_path=str(suite_p),
            candidate_version=saved.version,
            note="triggered via pa chat",
        )
        save_eval_run(run)
        append_event(
            ContextEvent.now(
                "eval",
                f"eval {slug} (via chat): {passed}/{n} pass",
                slug=slug,
                run_id=run.run_id,
            )
        )
    except Exception:
        pass
    return summary, {"passed": passed, "total": n, "results": [r.__dict__ for r in results]}


def _action_diagnose(args: dict) -> tuple[str, dict]:
    # We don't reimplement diagnose here — the LLM is told to fall back to
    # suggesting the user run `pa diagnose` if they want a full diagnosis.
    return (
        "diagnose in chat is read-only summary only. "
        "For full diagnosis, suggest: `pa diagnose <slug> --case <name> --suite <yaml>`",
        {"hint": "use CLI for full diagnose"},
    )


def _action_history(args: dict) -> tuple[str, dict]:
    slug = args.get("slug")
    if not slug:
        return "history: missing 'slug'", {"error": "missing slug"}
    runs = list_eval_runs(slug)
    if not runs:
        return f"No eval history for '{slug}'.", {"runs": []}
    rows = [
        {
            "run_id": r.run_id,
            "timestamp": r.timestamp,
            "version": r.candidate_version,
            "pass_rate": r.pass_rate,
            "avg_score": r.avg_score,
        }
        for r in runs[:10]
    ]
    table = "\n".join(
        f"  {r['timestamp']}  v{r['version']}  {r['pass_rate']*100:.0f}% pass  {r['avg_score']:.2f} avg"
        for r in rows
    )
    return f"Eval history for '{slug}' (most recent 10):\n{table}", {"runs": rows}


def _action_fork(args: dict) -> tuple[str, dict]:
    src = args.get("source")
    name = args.get("name")
    if not src or not name:
        return "fork: need 'source' and 'name'", {"error": "missing args"}
    try:
        new_saved = fork_prompt(slugify(src), name)
    except FileNotFoundError as e:
        return f"fork: {e}", {"error": str(e)}
    append_event(
        ContextEvent.now("fork", f"forked {src} → {new_saved.slug}", slug=new_saved.slug, source=src)
    )
    return f"Forked {src} → {new_saved.slug} v{new_saved.version}", {"slug": new_saved.slug}


def _action_save(args: dict) -> tuple[str, dict]:
    path = args.get("path")
    if not path:
        return "save: missing 'path'", {"error": "missing path"}
    p = Path(path)
    if not p.exists():
        return f"save: file not found: {path}", {"error": "not found"}
    saved = save_from_file(p)
    append_event(
        ContextEvent.now("save", f"imported '{saved.name}' from {p.name}", slug=saved.slug)
    )
    return f"Imported: {saved.slug} v{saved.version}", {"slug": saved.slug}


# ---------------------------------------------------------------------------
# Chat context and prompt
# ---------------------------------------------------------------------------

@dataclass
class ChatContext:
    client: PromptClient
    preferences: Preferences
    store: MemoryStore
    history: list[dict] = field(default_factory=list)  # {role, content}


CHAT_SYSTEM_PROMPT = """# Role
你是 prompt-agent 的对话式助手。开发者通过 `pa chat` 启动一个交互式 REPL，目的是快速设计、调试、迭代 system prompt，**不需要记住一堆 CLI 命令**。

# 你的能力
你可以调用以下 actions（每个会执行真实操作并把结果反馈给你）：

- `show` — 显示一个 prompt 的当前内容
  - args: `slug`, 可选 `version`
- `list` — 列出 library 里的 prompts
  - args: 可选 `tag` 或 `keyword`
- `eval` — 跑一个测试套件
  - args: `slug`, `suite` (yaml 文件路径)
- `history` — 查看某个 slug 历次 eval 结果
  - args: `slug`
- `fork` — 复制一个 prompt 作为起点
  - args: `source` (源 slug), `name` (新名字)
- `save` — 从外部文件导入一个 prompt
  - args: `path`

# 不支持的动作
- `new` / `edit` / `diagnose` 的完整功能 — 这些是 CLI 命令，让用户去跑
  - 如果用户想做这些，告诉他们具体命令，例如 `pa new "..."` 或 `pa diagnose <slug> --case <name> --suite <yaml>`

# 输出格式
你可以用自然语言回复。**当你需要执行动作时**，在回复末尾附一个 markdown 代码块：

```pa-action
{{"action": "show", "slug": "classifier", "rationale": "用户想看 classifier 当前内容"}}
```

可以加 `rationale` 字段（任意字符串）说明你的意图。**只输出一个 action 块**——REPL 会按顺序执行。

# 风格
- 中文回复（用户偏好 chat_persona=concise-zh）
- 简洁、面向开发者
- 不要重复用户已经说过的话
- 引用 action 结果时给出**具体内容片段**，不要泛泛而谈

# 上下文
{preferences}
{recent_activity}
"""


def _build_system_prompt(prefs: Preferences, recent: str) -> str:
    prefs_block = (
        "## User preferences\n"
        f"- techniques: {', '.join(prefs.preferred_techniques) or '(no preferences yet)'}\n"
        f"- avoided: {', '.join(prefs.avoided_techniques) or '-'}\n"
        f"- default tags: {', '.join(prefs.default_tags) or '-'}\n"
        f"- chat persona: {prefs.chat_persona}\n"
    )
    return CHAT_SYSTEM_PROMPT.format(preferences=prefs_block, recent_activity=recent)


# ---------------------------------------------------------------------------
# REPL loop
# ---------------------------------------------------------------------------

BANNER = """\
┌─ prompt-agent chat ──────────────────────────────────────────┐
│  Type natural-language requests. Use /help for tips.         │
│  Commands: /help /quit /list /show <slug> /history <slug>    │
│           /prefs [key=value ...]                             │
└──────────────────────────────────────────────────────────────┘\
"""


HELP_TEXT = """\
Available slash commands (in addition to natural language):
  /help               — show this help
  /quit, /exit, Ctrl-D — leave the chat
  /list [tag|keyword] — list library prompts
  /show <slug>        — show a prompt's current content
  /history <slug>     — show last 10 eval runs for a prompt
  /prefs [k=v ...]    — view or set preferences (no args = view; k=v = set)
  /prefs --clear      — reset preferences to defaults

Examples of natural-language requests:
  "看看 classifier 的当前内容"
  "fork 一份 classifier 出来叫 my-classifier"
  "用默认 suite 跑一下 safety-guard 的 eval"
  "我最近在调哪些 prompt"
"""


def _handle_slash(line: str, ctx: ChatContext) -> bool:
    """Handle /commands locally. Returns True if handled (do not send to LLM)."""
    if not line.startswith("/"):
        return False
    parts = line.split()
    cmd = parts[0].lower()
    if cmd in ("/quit", "/exit"):
        typer.echo("Bye.")
        raise SystemExit(0)
    if cmd == "/help":
        typer.echo(HELP_TEXT)
        return True
    if cmd == "/list":
        arg = parts[1] if len(parts) > 1 else None
        if arg and "=" not in arg:
            text, _ = _action_list({"keyword": arg})
        else:
            text, _ = _action_list({})
        typer.echo(text)
        return True
    if cmd == "/show":
        if len(parts) < 2:
            typer.echo("usage: /show <slug>")
            return True
        text, _ = _action_show({"slug": parts[1]})
        typer.echo(text)
        return True
    if cmd == "/history":
        if len(parts) < 2:
            typer.echo("usage: /history <slug>")
            return True
        text, _ = _action_history({"slug": parts[1]})
        typer.echo(text)
        return True
    if cmd == "/prefs":
        _handle_prefs_cmd(parts[1:], ctx)
        return True
    typer.echo(f"unknown command: {cmd} (try /help)")
    return True


def _handle_prefs_cmd(args: list[str], ctx: ChatContext) -> None:
    if not args:
        typer.echo("Preferences:")
        typer.echo(f"  preferred_techniques = {ctx.preferences.preferred_techniques}")
        typer.echo(f"  avoided_techniques    = {ctx.preferences.avoided_techniques}")
        typer.echo(f"  default_tags          = {ctx.preferences.default_tags}")
        typer.echo(f"  naming_pattern        = {ctx.preferences.naming_pattern!r}")
        typer.echo(f"  meta_prompt_style     = {ctx.preferences.meta_prompt_style!r}")
        typer.echo(f"  chat_persona          = {ctx.preferences.chat_persona!r}")
        return
    if args == ["--clear"]:
        from prompt_agent.memory import save_preferences
        save_preferences(Preferences())
        ctx.preferences = Preferences()
        typer.echo("Preferences reset to defaults.")
        return
    for a in args:
        if "=" not in a:
            typer.echo(f"ignore: {a} (expected key=value)")
            continue
        k, v = a.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k in ("preferred_techniques", "avoided_techniques", "default_tags"):
            current = list(getattr(ctx.preferences, k))
            current.append(v)
            setattr(ctx.preferences, k, current)
        elif k == "naming_pattern":
            ctx.preferences.naming_pattern = v
        elif k == "meta_prompt_style":
            ctx.preferences.meta_prompt_style = v
        elif k == "chat_persona":
            ctx.preferences.chat_persona = v
        else:
            ctx.preferences.extra[k] = v
    from prompt_agent.memory import save_preferences
    save_preferences(ctx.preferences)
    typer.echo("Preferences saved.")


def _dispatch_action(action: Action, ctx: ChatContext) -> tuple[str, dict]:
    handlers = {
        "show": lambda: _action_show(action.args),
        "list": lambda: _action_list(action.args),
        "eval": lambda: _action_eval(action.args, ctx),
        "diagnose": lambda: _action_diagnose(action.args),
        "history": lambda: _action_history(action.args),
        "fork": lambda: _action_fork(action.args),
        "save": lambda: _action_save(action.args),
    }
    handler = handlers.get(action.name)
    if handler is None:
        return (
            f"unknown action: {action.name!r}. Supported: {sorted(handlers)}",
            {"error": "unknown action", "supported": sorted(handlers)},
        )
    return handler()


def _chat_loop(ctx: ChatContext) -> None:
    typer.echo(BANNER)
    if ctx.history:
        typer.echo(f"[dim]Loaded {len(ctx.history)} prior messages.[/dim]")
    typer.echo("")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nBye.")
            return
        if not line:
            continue
        if _handle_slash(line, ctx):
            continue
        # Send to LLM
        ctx.history.append({"role": "user", "content": line})
        try:
            reply = ctx.client.chat(messages=ctx.history, system=_build_system_prompt(
                ctx.preferences, summarize_recent(10)
            ))
        except PromptGenerationError as e:
            typer.echo(f"[red]error:[/red] {e}")
            ctx.history.pop()  # don't keep the failed turn
            continue
        ctx.history.append({"role": "assistant", "content": reply})
        action = _parse_action(reply)
        prose = _strip_action_block(reply)
        if prose:
            typer.echo(f"\npa> {prose}\n")
        if action is None:
            continue
        if action.rationale:
            typer.echo(f"[dim]→ {action.name}: {action.rationale}[/dim]")
        text, payload = _dispatch_action(action, ctx)
        typer.echo(f"\n[bold]action result:[/bold]\n{text}\n")
        # Feed result back to the LLM for follow-up reasoning.
        ctx.history.append(
            {
                "role": "user",
                "content": f"[system: action {action.name!r} returned]\n{text}\n{payload if isinstance(payload, dict) else json.dumps(payload, ensure_ascii=False)}",
            }
        )


def chat(
    model: str | None = typer.Option(None, "--model", "-m", help="Override the chat model."),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume from a saved conversation (not yet implemented; placeholder)."),
) -> None:
    """Start the interactive REPL."""
    ensure_global_dirs()
    cfg = load_config()
    try:
        client = PromptClient(model=model or cfg.llm.default_model)
    except PromptGenerationError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)
    prefs = load_preferences()
    store = MemoryStore()
    ctx = ChatContext(client=client, preferences=prefs, store=store)
    try:
        _chat_loop(ctx)
    except SystemExit:
        # Save the session as a context event
        try:
            append_event(
                ContextEvent.now("chat", f"chat session ended ({len(ctx.history)} turns)")
            )
        except Exception:
            pass
        raise
