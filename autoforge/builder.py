"""Builder that generates code from a plan using Claude."""

from __future__ import annotations

from pathlib import Path

import click

from autoforge.config import CODE_MODEL
from autoforge.llm import LLMClient, validate_python_syntax
from autoforge.planner import Plan, PlanStep
from autoforge.project import Project
from autoforge.spec import ProjectSpec


BUILD_STEP_PROMPT = """You are building a software project step by step. Generate the code \
for the current step.

## Project: {project_name}
## Language: {language}
## Framework: {framework}

## Full File Tree
{file_tree}

## Current Step
Step {step_id}: {step_description}
Files to create/modify: {step_files}
Acceptance criteria: {acceptance_criteria}

{context}

## Instructions
Generate the complete file contents for each file listed in this step. \
Use this exact format for EACH file:

=== FILE: path/to/file.py ===
file contents here
=== END FILE ===

Generate ALL files needed for this step. Write clean, working code — no placeholders or TODOs. \
Every file must be complete and functional."""


class Builder:
    """Generates code from a plan, one step at a time."""

    def __init__(self, llm: LLMClient, project: Project, spec: ProjectSpec) -> None:
        self.llm = llm
        self.project = project
        self.spec = spec

    def build(self, plan: Plan) -> list[int]:
        """Execute all plan steps. Returns list of failed step IDs."""
        failed_steps = []

        for step in plan.steps:
            click.echo(f"\n  Step {step.id}: {step.description}")
            try:
                self._execute_step(step, plan)
                plan.mark_done(step.id)
                self.project.commit(f"Step {step.id}: {step.description}")
                click.echo(f"  Step {step.id}: Done")
            except Exception as e:
                click.echo(f"  Step {step.id}: FAILED - {e}")
                failed_steps.append(step.id)

        # Install dependencies after all files are written
        click.echo("\n  Installing dependencies...")
        self.project.install_deps()
        self.project.commit("Install dependencies")

        return failed_steps

    def _execute_step(self, step: PlanStep, plan: Plan) -> None:
        """Generate and write code for a single plan step."""
        # Build context from existing files that are relevant
        context = self._build_context(step, plan)

        prompt = BUILD_STEP_PROMPT.format(
            project_name=plan.project_name,
            language=self.spec.language,
            framework=self.spec.framework,
            file_tree="\n".join(f"  - {f}" for f in plan.file_tree),
            step_id=step.id,
            step_description=step.description,
            step_files=", ".join(step.file_paths),
            acceptance_criteria=step.acceptance_criteria,
            context=context,
        )

        response = self.llm.generate_code(prompt, model=CODE_MODEL)
        files = parse_file_blocks(response)

        if not files:
            # Fallback: if no file markers, treat the whole response as a single file
            if len(step.file_paths) == 1:
                files = {step.file_paths[0]: response}
            else:
                raise ValueError(f"Could not parse file blocks from LLM response for step {step.id}")

        for file_path, content in files.items():
            # Validate Python syntax
            if file_path.endswith(".py"):
                valid, error = validate_python_syntax(content)
                if not valid:
                    click.echo(f"    Warning: syntax issue in {file_path}: {error}")
                    # Still write it — the refinement loop will fix it

            self.project.write_file(file_path, content)
            click.echo(f"    Wrote {file_path}")

    def _build_context(self, step: PlanStep, plan: Plan) -> str:
        """Build context from existing project files relevant to this step."""
        context_parts = []
        existing_files = self.project.list_files()

        # Include files that are imported or referenced by the step's files
        for file_path in existing_files:
            if file_path in ("README.md",):
                continue
            content = self.project.read_file(file_path)
            if content and len(content) < 5000:  # Don't include huge files
                context_parts.append(
                    f"## Existing file: {file_path}\n```\n{content}\n```"
                )

        if context_parts:
            return "## Existing Project Files\n" + "\n\n".join(context_parts)
        return ""


def parse_file_blocks(text: str) -> dict[str, str]:
    """Parse === FILE: path === ... === END FILE === blocks from LLM output."""
    files: dict[str, str] = {}
    lines = text.splitlines()
    current_file = None
    current_content: list[str] = []

    for line in lines:
        if line.startswith("=== FILE:") and line.endswith("==="):
            if current_file:
                files[current_file] = "\n".join(current_content)
            current_file = line[len("=== FILE:"):].rstrip("=").strip()
            current_content = []
        elif line.strip() == "=== END FILE ===" and current_file:
            files[current_file] = "\n".join(current_content)
            current_file = None
            current_content = []
        elif current_file is not None:
            current_content.append(line)

    # Handle case where last file block wasn't closed
    if current_file and current_content:
        files[current_file] = "\n".join(current_content)

    return files
