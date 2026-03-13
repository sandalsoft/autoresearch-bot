"""Test runner and task executor for generated projects."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from autoforge.spec import EvalTask


@dataclass
class TestResult:
    """Result of running tests."""

    passed: bool
    output: str
    num_passed: int = 0
    num_failed: int = 0
    error: str = ""


@dataclass
class TaskResult:
    """Result of running a single evaluation task."""

    task_name: str
    command: str
    output: str
    exit_code: int
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class TestRunner:
    """Runs tests and evaluation tasks in generated projects."""

    def __init__(self, project_path: Path, timeout: int = 60) -> None:
        self.project_path = project_path
        self.timeout = timeout

    def run_tests(self, test_command: str) -> TestResult:
        """Run the project's test suite."""
        try:
            result = subprocess.run(
                test_command,
                shell=True,
                cwd=self.project_path,
                timeout=self.timeout,
                capture_output=True,
                text=True,
            )
            output = result.stdout + "\n" + result.stderr
            passed = result.returncode == 0

            # Try to extract pass/fail counts from common test runners
            num_passed, num_failed = self._parse_test_counts(output)

            return TestResult(
                passed=passed,
                output=output.strip(),
                num_passed=num_passed,
                num_failed=num_failed,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False,
                output="",
                error=f"Test command timed out after {self.timeout}s",
            )
        except Exception as e:
            return TestResult(
                passed=False,
                output="",
                error=str(e),
            )

    def run_task(self, task: EvalTask) -> TaskResult:
        """Run a single evaluation task."""
        try:
            result = subprocess.run(
                task.command,
                shell=True,
                cwd=self.project_path,
                timeout=self.timeout,
                capture_output=True,
                text=True,
            )
            return TaskResult(
                task_name=task.name,
                command=task.command,
                output=(result.stdout + "\n" + result.stderr).strip(),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return TaskResult(
                task_name=task.name,
                command=task.command,
                output=f"Task timed out after {self.timeout}s",
                exit_code=-1,
                timed_out=True,
            )
        except Exception as e:
            return TaskResult(
                task_name=task.name,
                command=task.command,
                output=str(e),
                exit_code=-1,
            )

    def run_all_tasks(self, tasks: list[EvalTask]) -> list[TaskResult]:
        """Run all evaluation tasks and return results."""
        return [self.run_task(task) for task in tasks]

    def _parse_test_counts(self, output: str) -> tuple[int, int]:
        """Best-effort extraction of test pass/fail counts from output."""
        import re

        # pytest: "5 passed, 2 failed"
        m = re.search(r"(\d+) passed", output)
        passed = int(m.group(1)) if m else 0
        m = re.search(r"(\d+) failed", output)
        failed = int(m.group(1)) if m else 0

        if passed or failed:
            return passed, failed

        # Jest/mocha: "Tests: 5 passed, 2 failed"
        m = re.search(r"Tests:\s+(\d+)\s+passed,\s+(\d+)\s+failed", output)
        if m:
            return int(m.group(1)), int(m.group(2))

        return 0, 0
