"""Forge refinement loop — test, evaluate, refine, repeat."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import click

from autoforge.evaluator import EvalResult, Evaluator
from autoforge.llm import LLMClient
from autoforge.project import Project
from autoforge.refiner import Refiner
from autoforge.runner import TestRunner
from autoforge.spec import ProjectSpec


@dataclass
class IterationLog:
    """Log entry for a single loop iteration."""

    iteration: int
    tests_passed: bool
    criteria_passed: list[str]
    criteria_failed: list[str]
    files_modified: list[str]
    reverted: bool = False
    skipped_criteria: list[str] = field(default_factory=list)


@dataclass
class ForgeState:
    """Checkpointable state for the forge loop."""

    iteration: int = 0
    completed: bool = False
    success: bool = False
    iterations: list[dict] = field(default_factory=list)
    failed_attempts: list[str] = field(default_factory=list)
    strike_counts: dict[str, int] = field(default_factory=dict)
    skipped_criteria: list[str] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> ForgeState:
        data = json.loads(path.read_text())
        return cls(**data)


class ForgeLoop:
    """Orchestrates the test/evaluate/refine cycle."""

    def __init__(
        self,
        llm: LLMClient,
        project: Project,
        spec: ProjectSpec,
        max_iterations: int = 10,
        max_strikes: int = 3,
    ) -> None:
        self.llm = llm
        self.project = project
        self.spec = spec
        self.max_iterations = max_iterations
        self.max_strikes = max_strikes
        self.runner = TestRunner(project.path, timeout=60)
        self.evaluator = Evaluator(llm)
        self.refiner = Refiner(llm, project)
        self.state = ForgeState()

    def run(self, state: ForgeState | None = None) -> ForgeState:
        """Run the refinement loop. Returns final state."""
        if state:
            self.state = state

        click.echo("\n" + "=" * 60)
        click.echo("  REFINEMENT LOOP")
        click.echo("=" * 60)

        while self.state.iteration < self.max_iterations:
            self.state.iteration += 1
            click.echo(f"\n--- Iteration {self.state.iteration}/{self.max_iterations} ---")

            log = self._run_iteration()
            self.state.iterations.append(asdict(log))

            # Checkpoint
            state_path = self.project.path / "forge_state.json"
            self.state.save(state_path)

            if log.reverted:
                click.echo("  Reverted due to regression.")
                continue

            # Check if we're done
            if self._check_success(log):
                self.state.completed = True
                self.state.success = True
                click.echo("\n  All criteria met! Stopping loop.")
                break

        if not self.state.success:
            click.echo(f"\n  Max iterations ({self.max_iterations}) reached.")
            self.state.completed = True

        return self.state

    def _run_iteration(self) -> IterationLog:
        """Run a single iteration of the loop."""
        # 1. Run tests
        click.echo("  Running tests...")
        test_result = self.runner.run_tests(self.spec.test_command)
        click.echo(f"  Tests: {'PASS' if test_result.passed else 'FAIL'}")

        # 2. Run evaluation tasks (skip tasks that have been permanently skipped)
        active_tasks = [
            t for t in self.spec.eval_tasks
            if t.name not in self.state.skipped_criteria
        ]
        click.echo(f"  Running {len(active_tasks)} eval tasks...")
        task_results = self.runner.run_all_tasks(active_tasks)

        # 3. Evaluate
        eval_result = self.evaluator.evaluate(test_result, task_results, active_tasks)
        click.echo(eval_result.summary())

        # 4. Check if everything passes
        if eval_result.all_passed:
            return IterationLog(
                iteration=self.state.iteration,
                tests_passed=True,
                criteria_passed=list(eval_result.passing_criteria),
                criteria_failed=[],
                files_modified=[],
                skipped_criteria=list(self.state.skipped_criteria),
            )

        # 5. Remember what was passing before refinement
        passing_before = eval_result.passing_criteria.copy()

        # 6. Refine
        click.echo("  Refining...")
        modified = self.refiner.refine(eval_result, self.state.failed_attempts)

        if not modified:
            click.echo("  No changes suggested.")
            return IterationLog(
                iteration=self.state.iteration,
                tests_passed=test_result.passed,
                criteria_passed=list(eval_result.passing_criteria),
                criteria_failed=list(eval_result.failing_criteria),
                files_modified=[],
                skipped_criteria=list(self.state.skipped_criteria),
            )

        # 7. Commit the refinement
        self.project.commit(f"Refinement iteration {self.state.iteration}")

        # 8. Re-run tests to check for regression
        click.echo("  Checking for regressions...")
        retest = self.runner.run_tests(self.spec.test_command)
        retask = self.runner.run_all_tasks(active_tasks)
        reeval = self.evaluator.evaluate(retest, retask, active_tasks)

        # 9. Check for regression
        regressed = False
        if passing_before and not passing_before.issubset(reeval.passing_criteria):
            regressed = True
            lost = passing_before - reeval.passing_criteria
            click.echo(f"  REGRESSION: lost passing criteria: {lost}")

        if not retest.passed and test_result.passed:
            regressed = True
            click.echo("  REGRESSION: tests were passing, now failing")

        if regressed:
            # Revert and record failed attempt
            self.project.revert()
            attempt_desc = f"Iteration {self.state.iteration}: modified {modified}, caused regression"
            self.state.failed_attempts.append(attempt_desc)

            # Track strikes per failing criteria
            for criteria_name in eval_result.failing_criteria:
                count = self.state.strike_counts.get(criteria_name, 0) + 1
                self.state.strike_counts[criteria_name] = count
                if count >= self.max_strikes:
                    click.echo(f"  Skipping '{criteria_name}' after {count} failed attempts")
                    self.state.skipped_criteria.append(criteria_name)

            return IterationLog(
                iteration=self.state.iteration,
                tests_passed=test_result.passed,
                criteria_passed=list(passing_before),
                criteria_failed=list(eval_result.failing_criteria),
                files_modified=modified,
                reverted=True,
                skipped_criteria=list(self.state.skipped_criteria),
            )

        return IterationLog(
            iteration=self.state.iteration,
            tests_passed=retest.passed,
            criteria_passed=list(reeval.passing_criteria),
            criteria_failed=list(reeval.failing_criteria),
            files_modified=modified,
            skipped_criteria=list(self.state.skipped_criteria),
        )

    def _check_success(self, log: IterationLog) -> bool:
        """Check if all non-skipped criteria pass and tests pass."""
        if not log.tests_passed:
            return False
        # All non-skipped criteria must be in the passing set
        required = {
            t.name for t in self.spec.eval_tasks
            if t.name not in self.state.skipped_criteria
        }
        return required.issubset(set(log.criteria_passed))
