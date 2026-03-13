"""Tests for autoforge.loop — ForgeLoop logic with mocked dependencies."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoforge.evaluator import CriteriaResult, EvalResult
from autoforge.loop import ForgeLoop, ForgeState
from autoforge.runner import TaskResult, TestResult
from autoforge.spec import EvalTask, ProjectSpec


def _make_spec() -> ProjectSpec:
    return ProjectSpec(
        name="test-project",
        summary="Test",
        language="python",
        framework="none",
        features=["feature 1"],
        file_tree=["main.py"],
        test_command="pytest",
        eval_tasks=[
            EvalTask(name="basic", command="python main.py", success_criteria="runs ok"),
        ],
    )


def _make_loop(tmpdir: str, spec: ProjectSpec | None = None) -> ForgeLoop:
    spec = spec or _make_spec()
    mock_llm = MagicMock()
    project = MagicMock()
    project.path = Path(tmpdir)
    project.commit = MagicMock(return_value=True)
    project.revert = MagicMock()

    loop = ForgeLoop(
        llm=mock_llm,
        project=project,
        spec=spec,
        max_iterations=3,
        max_strikes=2,
    )
    return loop


class TestForgeLoopStopsOnSuccess:
    def test_stops_when_all_pass(self, tmp_path):
        loop = _make_loop(str(tmp_path))

        # Mock runner to always pass
        loop.runner.run_tests = MagicMock(
            return_value=TestResult(passed=True, output="all passed", num_passed=1)
        )
        loop.runner.run_all_tasks = MagicMock(
            return_value=[TaskResult(task_name="basic", command="python main.py", output="ok", exit_code=0)]
        )

        # Mock evaluator to always pass
        loop.evaluator.evaluate = MagicMock(
            return_value=EvalResult(
                tests_passed=True,
                test_output="all passed",
                criteria_results=[
                    CriteriaResult(task_name="basic", passed=True, reasoning="looks good")
                ],
            )
        )

        state = loop.run()
        assert state.success is True
        assert state.iteration == 1  # Stopped on first iteration


class TestForgeLoopCapsIterations:
    def test_stops_at_max(self, tmp_path):
        loop = _make_loop(str(tmp_path))

        # Mock runner
        loop.runner.run_tests = MagicMock(
            return_value=TestResult(passed=True, output="passed")
        )
        loop.runner.run_all_tasks = MagicMock(
            return_value=[TaskResult(task_name="basic", command="cmd", output="bad", exit_code=1)]
        )

        # Mock evaluator to always fail
        loop.evaluator.evaluate = MagicMock(
            return_value=EvalResult(
                tests_passed=True,
                test_output="passed",
                criteria_results=[
                    CriteriaResult(task_name="basic", passed=False, reasoning="not good")
                ],
            )
        )

        # Mock refiner to do nothing
        loop.refiner.refine = MagicMock(return_value=[])

        state = loop.run()
        assert state.success is False
        assert state.iteration == 3  # Hit max_iterations


class TestForgeLoopRevertsRegression:
    def test_reverts_when_passing_tests_break(self, tmp_path):
        loop = _make_loop(str(tmp_path))
        call_count = 0

        def mock_run_tests(cmd):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                # First call: tests pass
                return TestResult(passed=True, output="passed")
            else:
                # After refinement: tests fail (regression)
                return TestResult(passed=False, output="FAILED")

        loop.runner.run_tests = MagicMock(side_effect=mock_run_tests)
        loop.runner.run_all_tasks = MagicMock(
            return_value=[TaskResult(task_name="basic", command="cmd", output="bad", exit_code=1)]
        )

        # First eval: tests pass, criteria fail
        # Second eval (after refine): tests fail (regression)
        eval_count = 0

        def mock_evaluate(test_result, task_results, tasks):
            nonlocal eval_count
            eval_count += 1
            if eval_count == 1:
                return EvalResult(
                    tests_passed=True,
                    test_output="passed",
                    criteria_results=[
                        CriteriaResult(task_name="basic", passed=False, reasoning="bad")
                    ],
                )
            return EvalResult(
                tests_passed=False,
                test_output="FAILED",
                criteria_results=[
                    CriteriaResult(task_name="basic", passed=False, reasoning="bad")
                ],
            )

        loop.evaluator.evaluate = MagicMock(side_effect=mock_evaluate)
        loop.refiner.refine = MagicMock(return_value=["main.py"])

        state = loop.run()
        # Should have called revert
        loop.project.revert.assert_called()
        assert len(state.failed_attempts) > 0


class TestForgeState:
    def test_save_load_roundtrip(self, tmp_path):
        state = ForgeState(
            iteration=5,
            completed=False,
            failed_attempts=["attempt 1"],
            strike_counts={"basic": 2},
        )
        path = tmp_path / "state.json"
        state.save(path)

        loaded = ForgeState.load(path)
        assert loaded.iteration == 5
        assert loaded.failed_attempts == ["attempt 1"]
        assert loaded.strike_counts == {"basic": 2}
