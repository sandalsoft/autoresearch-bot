"""Plan generation from project specification."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from autoforge.config import PLAN_MODEL
from autoforge.llm import LLMClient
from autoforge.spec import ProjectSpec


@dataclass
class PlanStep:
    """A single step in the implementation plan."""

    id: int
    description: str
    file_paths: list[str]
    acceptance_criteria: str
    done: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PlanStep:
        return cls(**data)


@dataclass
class Plan:
    """Complete implementation plan."""

    project_name: str
    summary: str
    file_tree: list[str]
    steps: list[PlanStep]

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "summary": self.summary,
            "file_tree": self.file_tree,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Plan:
        steps = [PlanStep.from_dict(s) for s in data.pop("steps", [])]
        return cls(steps=steps, **data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines = [
            f"# Implementation Plan: {self.project_name}",
            "",
            "## Summary",
            self.summary,
            "",
            "## File Tree",
        ]
        for path in self.file_tree:
            lines.append(f"- `{path}`")

        lines.extend(["", "## Steps"])
        for step in self.steps:
            check = "x" if step.done else " "
            lines.append(f"- [{check}] **Step {step.id}**: {step.description}")
            lines.append(f"  - Files: {', '.join(f'`{f}`' for f in step.file_paths)}")
            lines.append(f"  - Done when: {step.acceptance_criteria}")
            lines.append("")

        return "\n".join(lines) + "\n"

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "plan.md").write_text(self.to_markdown())
        (directory / "plan.json").write_text(self.to_json())

    @classmethod
    def load(cls, directory: Path) -> Plan:
        data = json.loads((directory / "plan.json").read_text())
        return cls.from_dict(data)

    def mark_done(self, step_id: int) -> None:
        for step in self.steps:
            if step.id == step_id:
                step.done = True
                return


PLAN_PROMPT = """You are an expert software architect. Generate a detailed, step-by-step \
implementation plan for the following project. Each step must be atomic (completable in a \
single pass), specific (exact file paths), and ordered (dependencies resolved).

## Project Specification
{spec_markdown}

## Requirements
- Generate 10-25 steps total
- Step 1 should be project scaffolding (directory structure, config files, dependency manifest)
- Include a step for writing tests
- The last step should be a validation/smoke test
- Each step should specify which files to create or modify
- Include dependency installation steps where needed
- The plan must include an explicit file tree for the project

Respond with JSON in this exact format:
{{
    "project_name": "{project_name}",
    "summary": "one paragraph summary of what we're building",
    "file_tree": ["path/to/file1.py", "path/to/file2.py"],
    "steps": [
        {{
            "id": 1,
            "description": "What to do in this step",
            "file_paths": ["path/to/file.py"],
            "acceptance_criteria": "What done looks like",
            "done": false
        }}
    ]
}}

Respond with ONLY the JSON."""


class Planner:
    """Generates implementation plans from project specifications."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def generate(self, spec: ProjectSpec) -> Plan:
        """Generate an implementation plan from a project spec."""
        prompt = PLAN_PROMPT.format(
            spec_markdown=spec.to_markdown(),
            project_name=spec.name,
        )

        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=PLAN_MODEL,
            max_tokens=8192,
        )

        # Parse JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        data = json.loads(raw)
        return Plan.from_dict(data)
