"""Integration tests for the pipeline with mocked LLM."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from autoforge.config import ForgeConfig
from autoforge.planner import Plan, PlanStep
from autoforge.spec import EvalTask, ProjectSpec


def _make_spec() -> ProjectSpec:
    return ProjectSpec(
        name="test-app",
        summary="A test app",
        language="python",
        framework="none",
        features=["hello world"],
        file_tree=["main.py", "tests/test_main.py"],
        test_command="python -m pytest",
        eval_tasks=[
            EvalTask(name="run app", command="python main.py", success_criteria="prints hello"),
        ],
    )


def _make_plan() -> Plan:
    return Plan(
        project_name="test-app",
        summary="A simple test app",
        file_tree=["main.py", "tests/test_main.py"],
        steps=[
            PlanStep(
                id=1,
                description="Create main.py",
                file_paths=["main.py"],
                acceptance_criteria="File exists and runs",
            ),
        ],
    )


class TestPlanGeneration:
    def test_plan_save_load(self, tmp_path):
        plan = _make_plan()
        plan.save(tmp_path)

        loaded = Plan.load(tmp_path)
        assert loaded.project_name == "test-app"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].description == "Create main.py"

    def test_plan_mark_done(self):
        plan = _make_plan()
        assert not plan.steps[0].done
        plan.mark_done(1)
        assert plan.steps[0].done

    def test_plan_to_markdown(self):
        plan = _make_plan()
        md = plan.to_markdown()
        assert "test-app" in md
        assert "main.py" in md
        assert "[ ]" in md

        plan.mark_done(1)
        md = plan.to_markdown()
        assert "[x]" in md


class TestSpecIntegration:
    def test_spec_with_eval_tasks(self):
        spec = _make_spec()
        assert len(spec.eval_tasks) == 1
        assert spec.eval_tasks[0].name == "run app"
        assert spec.test_command == "python -m pytest"

    def test_spec_save_load_with_tasks(self, tmp_path):
        spec = _make_spec()
        spec.save(tmp_path)
        loaded = ProjectSpec.load(tmp_path)
        assert len(loaded.eval_tasks) == 1
        assert loaded.eval_tasks[0].command == "python main.py"
