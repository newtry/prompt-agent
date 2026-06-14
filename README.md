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
    config.toml
    library/
        <slug>/
            v1.md          # versioned prompt (frontmatter + body)
            v2.md
            meta.toml      # slug, name, description, current_version, tags
    evals/<run-id>.json    # (future) raw eval trace history
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
        eval.py            # `pa eval <slug> --suite ...` (+ --baseline)
        version.py         # `pa version <slug>`
        library.py         # `pa library ...` (list/show/fork/save/seed)
    evaluators/
        schema.py          # TestCase + Suite YAML loader
        rule.py            # must_contain / must_not_contain checks
        llm_judge.py       # LLM-as-judge with rubric + JSON repair fallbacks
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

46 unit tests covering config, schema, library, rule evaluator, JSON repair, and meta prompts.

## Roadmap

- v0.2: diff visualization for `pa edit` (auto-show what changed before save)
- v0.3: store raw eval traces in `~/.prompt-agent/evals/` for historical regression tracking
- v0.4: web search integration for `pa new` (currently disabled in default config)
- v0.5: PyPI publish