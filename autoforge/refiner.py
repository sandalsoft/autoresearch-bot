"""Code refiner that generates targeted fixes based on evaluation results."""

from __future__ import annotations

import click

from autoforge.builder import parse_file_blocks
from autoforge.config import CODE_MODEL
from autoforge.evaluator import EvalResult
from autoforge.llm import LLMClient, validate_python_syntax
from autoforge.project import Project


REFINE_PROMPT = """You are fixing code in a software project based on test failures and \
evaluation feedback.

## Project Files
{project_files}

## Test Results
Tests passed: {tests_passed}
Test output (relevant portion):
```
{test_output}
```

## Evaluation Feedback
{eval_feedback}

## Previous Failed Attempts (DO NOT repeat these approaches)
{failed_attempts}

## Instructions
Generate MINIMAL, targeted fixes to address the failing tests and evaluation criteria. \
Only modify files that need changes. Do not rewrite files that are working correctly.

Use this exact format for EACH file you modify:

=== FILE: path/to/file.py ===
complete file contents here
=== END FILE ===

If no changes are needed, respond with "NO CHANGES NEEDED".
Generate ONLY the file blocks, no explanations."""


class Refiner:
    """Generates targeted code fixes from evaluation results."""

    def __init__(self, llm: LLMClient, project: Project) -> None:
        self.llm = llm
        self.project = project

    def refine(
        self,
        eval_result: EvalResult,
        failed_attempts: list[str],
    ) -> list[str]:
        """Generate and apply fixes. Returns list of modified file paths."""
        # Build project context (only relevant files, truncated)
        project_files = self._get_project_context()

        # Build failed attempts context
        attempts_text = "None" if not failed_attempts else "\n".join(
            f"- {a}" for a in failed_attempts
        )

        prompt = REFINE_PROMPT.format(
            project_files=project_files,
            tests_passed=eval_result.tests_passed,
            test_output=eval_result.test_output[-3000:] if eval_result.test_output else "No output",
            eval_feedback=eval_result.summary(),
            failed_attempts=attempts_text,
        )

        response = self.llm.generate_code(prompt, model=CODE_MODEL)

        if "NO CHANGES NEEDED" in response:
            return []

        files = parse_file_blocks(response)
        modified = []

        for file_path, content in files.items():
            if file_path.endswith(".py"):
                valid, error = validate_python_syntax(content)
                if not valid:
                    click.echo(f"    Warning: syntax issue in {file_path}: {error}")

            self.project.write_file(file_path, content)
            modified.append(file_path)
            click.echo(f"    Modified {file_path}")

        return modified

    def _get_project_context(self) -> str:
        """Get project files as context, truncating large files."""
        parts = []
        for file_path in self.project.list_files():
            if file_path in ("README.md",):
                continue
            content = self.project.read_file(file_path)
            if content is None:
                continue
            if len(content) > 8000:
                content = content[:8000] + "\n... (truncated)"
            parts.append(f"## {file_path}\n```\n{content}\n```")

        return "\n\n".join(parts) if parts else "No files yet."
