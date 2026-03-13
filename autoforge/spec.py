"""Project specification and evaluation task models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class EvalTask:
    """A user-defined evaluation task with success criteria."""

    name: str
    command: str  # Shell command to execute
    success_criteria: str  # Text description for LLM judge

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> EvalTask:
        return cls(**data)


@dataclass
class ProjectSpec:
    """Complete project specification from the discovery interview."""

    name: str
    summary: str
    language: str
    framework: str
    features: list[str]
    file_tree: list[str]  # Planned file paths
    test_command: str  # e.g. "pytest", "npm test"
    eval_tasks: list[EvalTask]
    architecture_notes: str = ""
    constraints: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ProjectSpec:
        tasks = [EvalTask.from_dict(t) for t in data.pop("eval_tasks", [])]
        return cls(eval_tasks=tasks, **data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines = [
            f"# Project Specification: {self.name}",
            "",
            f"## Summary",
            self.summary,
            "",
            "## Technical Decisions",
            f"- **Language**: {self.language}",
            f"- **Framework**: {self.framework}",
            f"- **Test Command**: `{self.test_command}`",
            "",
            "## Features",
        ]
        for feat in self.features:
            lines.append(f"- {feat}")

        lines.extend(["", "## File Tree"])
        for path in self.file_tree:
            lines.append(f"- `{path}`")

        if self.eval_tasks:
            lines.extend(["", "## Evaluation Tasks"])
            for task in self.eval_tasks:
                lines.append(f"### {task.name}")
                lines.append(f"- **Command**: `{task.command}`")
                lines.append(f"- **Success Criteria**: {task.success_criteria}")
                lines.append("")

        if self.architecture_notes:
            lines.extend(["", "## Architecture Notes", self.architecture_notes])

        if self.constraints:
            lines.extend(["", "## Constraints", self.constraints])

        return "\n".join(lines) + "\n"

    def save(self, directory: Path) -> None:
        """Save spec as both markdown and JSON to the given directory."""
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "spec.md").write_text(self.to_markdown())
        (directory / "spec.json").write_text(self.to_json())

    @classmethod
    def load(cls, directory: Path) -> ProjectSpec:
        """Load spec from JSON file in the given directory."""
        data = json.loads((directory / "spec.json").read_text())
        return cls.from_dict(data)
