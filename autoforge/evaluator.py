"""LLM-based evaluation of test results and task outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from autoforge.config import EVAL_MODEL
from autoforge.llm import LLMClient, truncate_output
from autoforge.runner import TaskResult, TestResult
from autoforge.spec import EvalTask


@dataclass
class CriteriaResult:
    """Result of evaluating a single criteria."""

    task_name: str
    passed: bool
    reasoning: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Overall evaluation result."""

    tests_passed: bool
    test_output: str
    criteria_results: list[CriteriaResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.tests_passed and all(c.passed for c in self.criteria_results)

    @property
    def passing_criteria(self) -> set[str]:
        return {c.task_name for c in self.criteria_results if c.passed}

    @property
    def failing_criteria(self) -> set[str]:
        return {c.task_name for c in self.criteria_results if not c.passed}

    def summary(self) -> str:
        lines = []
        lines.append(f"Tests: {'PASS' if self.tests_passed else 'FAIL'}")
        for cr in self.criteria_results:
            status = "PASS" if cr.passed else "FAIL"
            lines.append(f"  [{status}] {cr.task_name}: {cr.reasoning}")
        return "\n".join(lines)


class Evaluator:
    """Evaluates test results and task outputs using an LLM judge."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def evaluate(
        self,
        test_result: TestResult,
        task_results: list[TaskResult],
        eval_tasks: list[EvalTask],
    ) -> EvalResult:
        """Run full evaluation: tests + LLM-judged task criteria."""
        criteria_results = []
        all_suggestions = []

        # Match task results to eval tasks by name
        task_map = {tr.task_name: tr for tr in task_results}

        for eval_task in eval_tasks:
            task_result = task_map.get(eval_task.name)
            if not task_result:
                criteria_results.append(
                    CriteriaResult(
                        task_name=eval_task.name,
                        passed=False,
                        reasoning="Task was not executed",
                        suggestions=["Ensure the task command runs successfully"],
                    )
                )
                continue

            cr = self._judge_task(eval_task, task_result)
            criteria_results.append(cr)
            all_suggestions.extend(cr.suggestions)

        return EvalResult(
            tests_passed=test_result.passed,
            test_output=truncate_output(test_result.output),
            criteria_results=criteria_results,
            suggestions=all_suggestions,
        )

    def _judge_task(self, eval_task: EvalTask, task_result: TaskResult) -> CriteriaResult:
        """Use LLM to judge a task result against its success criteria."""
        prompt = (
            "You are evaluating whether a software task met its success criteria.\n\n"
            f"## Task: {eval_task.name}\n"
            f"## Command: `{eval_task.command}`\n"
            f"## Exit Code: {task_result.exit_code}\n"
            f"## Success Criteria: {eval_task.success_criteria}\n\n"
            f"## Task Output:\n```\n{truncate_output(task_result.output)}\n```\n\n"
            "Evaluate whether the output meets the success criteria. "
            "Respond with JSON:\n"
            '{"passed": true/false, "reasoning": "brief explanation", '
            '"suggestions": ["improvement 1", "improvement 2"]}\n'
            "Respond with ONLY the JSON."
        )

        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=EVAL_MODEL,
            max_tokens=1024,
        )

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        try:
            data = json.loads(raw)
            return CriteriaResult(
                task_name=eval_task.name,
                passed=data.get("passed", False),
                reasoning=data.get("reasoning", ""),
                suggestions=data.get("suggestions", []),
            )
        except json.JSONDecodeError:
            return CriteriaResult(
                task_name=eval_task.name,
                passed=False,
                reasoning=f"Could not parse evaluation response: {raw[:200]}",
                suggestions=["Re-run evaluation"],
            )
