# PromptAgent

CLI agent that helps agent developers design, test, and manage system prompts.

## What it does

A single-binary CLI for the full prompt-engineering workflow:

| Command         | Purpose                                                              |
| --------------- | -------------------------------------------------------------------- |
| `pa new`        | Generate a new system prompt from a natural-language description.     |
| `pa show`       | Print a prompt from the library (with frontmatter metadata).         |
| `pa edit`       | Open a prompt in `$EDITOR` to revise it.                             |
| `pa diagnose`   | Diagnose a failing prompt + case and propose a targeted fix.          |
| `pa eval`       | Run a YAML test suite against a prompt; supports baseline comparison. |
| `pa chat`       | Interactive REPL for prompt engineering (uses memory).                |
| `pa library`    | List / show / fork / save / seed prompts.                            |
| `pa version`    | Show version history and unified diffs.                               |

## Install

```bash
cd prompt-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

export ANTHROPIC_API_KEY=sk-ant-...   # or ANTHROPIC_AUTH_TOKEN
```

Requires Python 3.11+.

## Quickstart

```bash
# 1. Generate a new prompt
pa new "ReAct 代码 agent，能调用 ripgrep 搜索 monorepo 代码"

# 2. Generate with explicit name/tags
pa new "代码审查 agent" --name code-reviewer --tag agent --tag code

# 3. Run it through a test suite
pa eval code-reviewer --suite suites/code-reviewer.yaml

# 4. Compare a new version against an older one
pa eval code-reviewer --suite suites/code-reviewer.yaml --baseline 1

# 5. Diagnose a failure and get a fix proposal
pa diagnose code-reviewer --case "对抗输入" --suite suites/code-reviewer.yaml
```

## Commands in detail

### `pa new <description>`

Generate a new prompt using a 5-step meta prompt:
1. Decompose the user's stated task into elements (role / task / constraints / output / edge cases).
2. Pick techniques (CoT, few-shot, ReAct, structured output, etc.).
3. Compose the prompt draft.
4. Self-review against a 10-point checklist.
5. Emit a JSON envelope that the CLI persists as a versioned Markdown file.

```bash
pa new "客服 FAQ 分类 agent" --name classifier --tag nlp --tag classification --json
```

The `--json` flag prints the raw generated envelope (useful for piping).

### `pa show <slug>`

Print the current version of a prompt. Use `--version N` to print an older version.

### `pa edit <slug>`

Open the current version's Markdown file in `$EDITOR`. Save and exit to bump the version
automatically (the new version gets a fresh file; the old one is preserved).

### `pa diagnose <slug> --case <name> --suite <yaml>`

Point at a failing test case; the diagnose meta-prompt analyzes the agent's output against
the criteria and proposes a focused fix (specific lines, not a full rewrite). The fix can be
applied automatically as a new version.

### `pa eval <slug> --suite <yaml>`

Runs each test case through the agent model, then through an LLM judge. Final pass requires:
- Judge `overall_pass = true`
- All `criteria` pass
- `behavior_match` with `expected_behavior`
- No `must_not_contain` violations
- All `must_contain` substrings present

```bash
# Compare v3 against v1
pa eval code-reviewer --suite suites/code-reviewer.yaml --baseline 1
```

The comparison table highlights `IMPROVED` and `REGRESSED` cases (great for catching prompt
regressions when iterating).

### `pa library`

```bash
pa library list                              # all prompts in your local library
pa library show classifier                   # current version of a prompt
pa library show classifier --version 1       # an older version
pa library fork classifier my-classifier     # create a copy to experiment on
pa library save path/to/prompt.md            # import an external prompt

# Seed library (built-in high-quality starting points)
pa library seed list
pa library seed show sql-generator
pa library seed install --all                # install every seed into your local library
pa library seed install classifier           # install a specific seed
```

### `pa version <slug>`

List all versions of a prompt, show metadata, and display unified diffs between adjacent
versions.

### `pa chat`

Interactive REPL for prompt engineering. Talk naturally; the assistant dispatches to
existing commands (`show` / `list` / `eval` / `history` / `fork` / `save`) and consults
memory for your preferences and recent activity.

```
$ pa chat
┌─ prompt-agent chat ──────────────────────────────────────────┐
│  Type natural-language requests. Use /help for tips.         │
└──────────────────────────────────────────────────────────────┘
you> 帮我看一下 classifier 当前长什么样
pa> ```pa-action
{"action": "show", "slug": "classifier", "rationale": "用户想看 classifier 当前内容"}
```
[classifier v3]
  文本三分类（bug 报告 / 功能请求 / 一般问题），用 few-shot 示例锁定风格
  tags: classification, few-shot

[Role]...

you> 跑一下 eval，看它现在能拿几分
pa> 好的，调 eval。
```pa-action
{"action": "eval", "slug": "classifier", "suite": "...suite.yaml"}
```

Eval classifier v3 — 5/5 pass (100%)
  PASS  1.00  应该识别明显的 bug 报告
  ...

you> /history classifier
[shows last 10 eval runs from memory]
```

Slash commands (work without LLM roundtrip):

| Command | Purpose |
|---------|---------|
| `/help` | show slash-command help |
| `/quit`, `/exit`, Ctrl-D | leave the chat |
| `/list [tag|keyword]` | list library prompts |
| `/show <slug>` | show a prompt |
| `/history <slug>` | last 10 eval runs |
| `/prefs` | view preferences |
| `/prefs k=v k=v` | set preferences (e.g. `preferred_techniques=CoT`) |
| `/prefs --clear` | reset preferences |

The LLM is told to emit one `pa-action` JSON block per turn; the REPL parses it,
executes the underlying CLI action, and feeds the result back to the LLM so it can
reason about follow-up steps.

## Memory module

`pa` persists cross-session state to `~/.prompt-agent/`:

| Layer | File | Purpose |
|-------|------|---------|
| Preferences | `preferences.toml` | preferred techniques, default tags, chat persona |
| Eval history | `evals/<slug>/<run-id>.json` | every `pa eval` run (results, score, reasoning) — auto-saved |
| Context log | `context.jsonl` | append-only event stream (new / edit / fork / eval / diagnose / seed_install / chat) |
| Prompt library | `library/<slug>/v*.md` | (existing) versioned prompt files |

All `pa` commands write to context.jsonl automatically; `pa eval` also saves a full
run record. `pa chat` injects the last 10 events + your preferences into its system
prompt, so the assistant knows what you've been doing.

Inspect memory state:

```python
from prompt_agent.memory import load_recent_events, summarize_recent, list_eval_runs

events = load_recent_events(20)                # last 20 events
print(summarize_recent(10))                    # one-paragraph natural-language summary
runs = list_eval_runs("classifier")            # all eval runs for a slug
```

## Seed library

Six built-in seeds covering common patterns:

| Seed              | Pattern                                | Use case                         |
| ----------------- | -------------------------------------- | -------------------------------- |
| `classifier`      | Structured output (label only)         | Categorize user input            |
| `sql-generator`   | Structured output + safety rules       | Read-only SQL from natural lang  |
| `react-coder`     | ReAct format + tool refusal            | Code reasoning + tool isolation  |
| `doc-summarizer`  | Few-shot + fact-isolation              | Summarize documents faithfully   |
| `tool-router`     | Decision tree + single-tool selection  | Route user intent to one tool    |
| `safety-guard`    | Input isolation + structured verdict   | Pre-LLM safety filter            |

Each seed ships with a `v1.md` prompt AND a matching `suite.yaml` test suite, so you can
install a seed and immediately run `pa eval` against it.

## Test suite format

```yaml
- name: <case name>
  input:
    user: "<user message>"
    # or messages: [{role, content}, ...]
  expected:
    behavior: refuse | comply | partial
    criteria:
      - "<natural-language rubric item>"
    must_contain:
      - "<substring that must appear>"
    must_not_contain:
      - "<substring that must NOT appear>"
```

## Library layout

```
~/.prompt-agent/
    config.toml                  # global config (load order: env > project > global)
    preferences.toml             # user-level defaults (memory/preferences)
    context.jsonl                # append-only event log (memory/context)
    library/
        <slug>/
            v1.md                # versioned prompt (frontmatter + body)
            v2.md
            meta.toml            # slug, name, description, current_version, tags
    evals/
        <slug>/
            <run-id>.json        # one eval run record (memory/eval_history)
```

Each `vN.md` is a self-contained `python-frontmatter` Markdown file:

```markdown
---
name: code-reviewer
description: 严格的代码审查 agent，关注安全和可维护性
tags: [review, security]
techniques_used: [CoT, Few-shot, Negative Constraints]
rationale: ...
assumptions: [...]
trade_offs: ...
created: '2026-06-14'
---

# Role
...
```

## Config

Global: `~/.prompt-agent/config.toml`

```toml
[llm]
default_model = "claude-opus-4-7"
judge_model = "claude-sonnet-4-6"

[search]
enabled = true

[eval]
parallel = 4
```

Environment overrides: `PA_DEFAULT_MODEL`, `PA_JUDGE_MODEL`, `PA_SEARCH_ENABLED`,
`PA_EVAL_PARALLEL`.

## Architecture

```
src/prompt_agent/
    cli.py                 # Typer entry point; forced UTF-8 on Windows
    core/
        meta_prompt.py     # META_PROMPT (for `new`) + DIAGNOSE_META_PROMPT
        client.py          # Anthropic SDK wrapper; ANTHROPIC_API_KEY || AUTH_TOKEN
        config.py          # Config dataclass + loader (file → env → defaults)
    commands/
        new.py             # `pa new <description>`
        show.py            # `pa show <slug>`
        edit.py            # `pa edit <slug>`
        diagnose.py        # `pa diagnose <slug> --case ...`
        eval.py            # `pa eval <slug> --suite ...` (+ --baseline) — auto-saves run
        chat.py            # `pa chat` interactive REPL
        version.py         # `pa version <slug>`
        library.py         # `pa library ...` (list/show/fork/save/seed)
    evaluators/
        schema.py          # TestCase + Suite YAML loader
        rule.py            # must_contain / must_not_contain checks
        llm_judge.py       # LLM-as-judge with rubric + JSON repair fallbacks
    memory/                # cross-session state
        preferences.py     # ~/.prompt-agent/preferences.toml
        eval_history.py    # ~/.prompt-agent/evals/<slug>/<run-id>.json
        context.py         # ~/.prompt-agent/context.jsonl
        store.py           # MemoryStore facade
    storage/
        library.py         # filesystem-backed prompt library
    seed/
        <name>/
            v1.md          # bundled prompt
            suite.yaml     # bundled test suite
```

## JSON repair strategy

The LLM judge sometimes embeds unescaped ASCII `"` inside JSON string values (especially when
quoting the agent's output). `_extract_json` has three layers:

1. Direct `json.loads`
2. State-machine rewrite that replaces ASCII `"` embedded in a string with `'`
3. `json_repair` library as a last resort

This recovers almost all malformed outputs without making the judge prompt overly restrictive.

## Running the test suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

66 unit tests covering config, schema, library, rule evaluator, JSON repair, meta prompts, memory module, and chat action protocol.

## Roadmap

- v0.4: web search integration for `pa new` (currently disabled in default config)
- v0.5: PyPI publish
- v0.6: conversation persistence + `/resume` for `pa chat`