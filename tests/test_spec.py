"""Tests for autoforge.spec."""

import json
import tempfile
from pathlib import Path

from autoforge.spec import EvalTask, ProjectSpec


def _make_spec() -> ProjectSpec:
    return ProjectSpec(
        name="test-project",
        summary="A test project",
        language="python",
        framework="flask",
        features=["feature 1", "feature 2"],
        file_tree=["app.py", "tests/test_app.py"],
        test_command="pytest",
        eval_tasks=[
            EvalTask(
                name="health check",
                command="curl http://localhost:5000/health",
                success_criteria="Returns 200 OK with JSON body",
            )
        ],
        architecture_notes="Simple REST API",
        constraints="No database",
    )


def test_spec_to_dict():
    spec = _make_spec()
    d = spec.to_dict()
    assert d["name"] == "test-project"
    assert d["language"] == "python"
    assert len(d["eval_tasks"]) == 1
    assert d["eval_tasks"][0]["name"] == "health check"


def test_spec_from_dict():
    spec = _make_spec()
    d = spec.to_dict()
    restored = ProjectSpec.from_dict(d)
    assert restored.name == spec.name
    assert restored.language == spec.language
    assert len(restored.eval_tasks) == 1
    assert restored.eval_tasks[0].command == "curl http://localhost:5000/health"


def test_spec_json_roundtrip():
    spec = _make_spec()
    json_str = spec.to_json()
    data = json.loads(json_str)
    restored = ProjectSpec.from_dict(data)
    assert restored.name == spec.name
    assert restored.features == spec.features
    assert restored.eval_tasks[0].success_criteria == spec.eval_tasks[0].success_criteria


def test_spec_to_markdown():
    spec = _make_spec()
    md = spec.to_markdown()
    assert "# Project Specification: test-project" in md
    assert "python" in md
    assert "flask" in md
    assert "health check" in md
    assert "pytest" in md


def test_spec_save_load():
    spec = _make_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        spec.save(path)
        assert (path / "spec.md").exists()
        assert (path / "spec.json").exists()

        loaded = ProjectSpec.load(path)
        assert loaded.name == spec.name
        assert loaded.language == spec.language
        assert len(loaded.eval_tasks) == len(spec.eval_tasks)


def test_eval_task_roundtrip():
    task = EvalTask(name="test", command="echo hi", success_criteria="prints hi")
    d = task.to_dict()
    restored = EvalTask.from_dict(d)
    assert restored.name == task.name
    assert restored.command == task.command
