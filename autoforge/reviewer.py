"""Carmack-level plan review using Claude Opus."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import click

from autoforge.config import PLAN_MODEL
from autoforge.llm import LLMClient
from autoforge.planner import Plan
from autoforge.spec import ProjectSpec


@dataclass
class ReviewIssue:
    """A single issue found during review."""

    severity: str  # CRITICAL, IMPORTANT, MINOR, OBSERVATION
    description: str
    suggestion: str


@dataclass
class ReviewResult:
    """Result of a Carmack-level plan review."""

    issues: list[ReviewIssue] = field(default_factory=list)
    approved: bool = False
    summary: str = ""

    @property
    def has_critical(self) -> bool:
        return any(i.severity == "CRITICAL" for i in self.issues)

    @property
    def has_important(self) -> bool:
        return any(i.severity == "IMPORTANT" for i in self.issues)


REVIEW_PROMPT = """You are John Carmack reviewing an implementation plan. Think deeply about \
simplicity, correctness, and practical engineering tradeoffs.

## Project Specification
{spec_markdown}

## Implementation Plan
{plan_markdown}

Review this plan for:
1. Will it actually work end-to-end at runtime?
2. Are there missing pieces that will block execution?
3. Is anything over-engineered?
4. Are there subprocess issues or practical pitfalls?
5. Does the step ordering make sense (dependencies resolved)?
6. Are the file paths consistent?

Respond with JSON:
{{
    "issues": [
        {{
            "severity": "CRITICAL|IMPORTANT|MINOR|OBSERVATION",
            "description": "What the issue is",
            "suggestion": "How to fix it"
        }}
    ],
    "summary": "Overall assessment in 2-3 sentences"
}}

Respond with ONLY the JSON."""


REVISE_PROMPT = """Revise the following implementation plan to address these critical/important issues.

## Original Plan (JSON)
{plan_json}

## Issues to Address
{issues}

Return the COMPLETE revised plan as JSON in the same format as the original. \
Respond with ONLY the JSON."""


class PlanReviewer:
    """Carmack-level plan review using Claude Opus."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def review(self, plan: Plan, spec: ProjectSpec, max_rounds: int = 2) -> tuple[Plan, ReviewResult]:
        """Review and optionally revise a plan. Returns (possibly revised plan, review result)."""
        current_plan = plan

        for round_num in range(max_rounds):
            click.echo(f"\n  Review round {round_num + 1}...")
            result = self._do_review(current_plan, spec)

            # Print issues
            for issue in result.issues:
                icon = {"CRITICAL": "!!", "IMPORTANT": "!", "MINOR": "-", "OBSERVATION": "~"}
                click.echo(f"  [{icon.get(issue.severity, '?')}] {issue.severity}: {issue.description}")

            if not result.has_critical and not result.has_important:
                result.approved = True
                click.echo("  Plan approved.")
                return current_plan, result

            if round_num < max_rounds - 1:
                click.echo("  Revising plan to address issues...")
                current_plan = self._revise(current_plan, result)
            else:
                click.echo("  Max revision rounds reached. Proceeding with current plan.")
                result.approved = True  # Proceed anyway
                return current_plan, result

        return current_plan, result

    def _do_review(self, plan: Plan, spec: ProjectSpec) -> ReviewResult:
        prompt = REVIEW_PROMPT.format(
            spec_markdown=spec.to_markdown(),
            plan_markdown=plan.to_markdown(),
        )

        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=PLAN_MODEL,
            max_tokens=4096,
        )

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        data = json.loads(raw)
        issues = [ReviewIssue(**i) for i in data.get("issues", [])]
        return ReviewResult(
            issues=issues,
            summary=data.get("summary", ""),
        )

    def _revise(self, plan: Plan, result: ReviewResult) -> Plan:
        issues_text = "\n".join(
            f"- [{i.severity}] {i.description} → {i.suggestion}"
            for i in result.issues
            if i.severity in ("CRITICAL", "IMPORTANT")
        )

        prompt = REVISE_PROMPT.format(
            plan_json=plan.to_json(),
            issues=issues_text,
        )

        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=PLAN_MODEL,
            max_tokens=8192,
        )

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        data = json.loads(raw)
        return Plan.from_dict(data)
