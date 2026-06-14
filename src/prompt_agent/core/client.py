"""Anthropic SDK wrapper for prompt generation and diagnosis."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import yaml

from prompt_agent.core.meta_prompt import DIAGNOSE_META_PROMPT, META_PROMPT


@dataclass
class GeneratedPrompt:
    prompt: str
    rationale: str
    techniques_used: list[str]
    assumptions: list[str]
    trade_offs: str
    checklist_results: dict[str, str]


@dataclass
class Issue:
    severity: str
    category: str
    location: str
    problem: str
    fix: str
    replacement: str


@dataclass
class DiagnosisReport:
    summary: str
    issues: list[Issue]
    root_cause_analysis: str
    suggested_rewrite: str
    checklist_results: dict[str, str]


class PromptGenerationError(Exception):
    """Raised when the LLM output cannot be parsed."""


_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _extract_json_block(text: str) -> str:
    """Extract the first ```json ... ``` block from LLM output."""
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        raise PromptGenerationError(
            "No JSON block found in LLM output. Raw output:\n" + text[:500]
        )
    return match.group(1)


def _parse_response(text: str) -> GeneratedPrompt:
    raw = _extract_json_block(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PromptGenerationError(f"Invalid JSON in LLM output: {e}\nRaw: {raw[:500]}") from e

    required = {"prompt", "rationale", "techniques_used", "assumptions", "trade_offs", "checklist_results"}
    missing = required - set(data.keys())
    if missing:
        raise PromptGenerationError(f"LLM output missing required fields: {missing}")

    return GeneratedPrompt(
        prompt=data["prompt"],
        rationale=data["rationale"],
        techniques_used=list(data["techniques_used"]),
        assumptions=list(data["assumptions"]),
        trade_offs=data["trade_offs"],
        checklist_results=dict(data["checklist_results"]),
    )


def _parse_diagnosis(text: str) -> DiagnosisReport:
    raw = _extract_json_block(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PromptGenerationError(f"Invalid JSON in LLM output: {e}\nRaw: {raw[:500]}") from e

    required = {"summary", "issues", "root_cause_analysis", "suggested_rewrite", "checklist_results"}
    missing = required - set(data.keys())
    if missing:
        raise PromptGenerationError(f"LLM output missing required fields: {missing}")

    issues = [
        Issue(
            severity=i.get("severity", "unknown"),
            category=i.get("category", ""),
            location=i.get("location", ""),
            problem=i.get("problem", ""),
            fix=i.get("fix", ""),
            replacement=i.get("replacement", ""),
        )
        for i in data["issues"]
    ]

    return DiagnosisReport(
        summary=data["summary"],
        issues=issues,
        root_cause_analysis=data["root_cause_analysis"],
        suggested_rewrite=data["suggested_rewrite"],
        checklist_results=dict(data["checklist_results"]),
    )


def _read_failure_case(path: Path) -> str:
    """Load failure case file (JSON or YAML) as a string for the prompt."""
    text = path.read_text(encoding="utf-8")
    # Try JSON first, then YAML; we just pass the raw text in either case
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(text)
            return yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)
        except yaml.YAMLError:
            # Raw text — pass through
            return text


class PromptClient:
    """Thin wrapper around the Anthropic SDK for prompt operations."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (
            api_key
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_AUTH_TOKEN")
        )
        if not self.api_key:
            raise PromptGenerationError(
                "No API key found. Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN, "
                "or pass api_key explicitly."
            )
        self.model = model or "claude-opus-4-7"
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def generate(self, description: str) -> GeneratedPrompt:
        """Generate a system prompt from a natural-language description."""
        message = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=META_PROMPT,
            messages=[{"role": "user", "content": description}],
        )
        text = message.content[0].text
        return _parse_response(text)

    def diagnose(self, prompt_text: str, failure_case: str | None = None) -> DiagnosisReport:
        """Diagnose an existing prompt, optionally with a failure case."""
        user_msg = f"# 待诊断 prompt\n```\n{prompt_text}\n```"
        if failure_case:
            user_msg += f"\n\n# 失败 case\n```json\n{failure_case}\n```"
        message = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=DIAGNOSE_META_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = message.content[0].text
        return _parse_diagnosis(text)