"""Main pipeline orchestrating the full Autoforge lifecycle."""

from __future__ import annotations

from pathlib import Path

import click

from autoforge.builder import Builder
from autoforge.config import ForgeConfig
from autoforge.interviewer import Interviewer
from autoforge.llm import LLMClient
from autoforge.loop import ForgeLoop, ForgeState
from autoforge.planner import Planner
from autoforge.project import Project
from autoforge.reviewer import PlanReviewer
from autoforge.spec import ProjectSpec


class ForgePipeline:
    """Wires together the full Autoforge lifecycle."""

    def __init__(self, config: ForgeConfig) -> None:
        self.config = config
        self.llm = LLMClient(config)

    def run(self, idea: str) -> None:
        """Execute the full lifecycle: Interview → Plan → Review → Build → Loop."""
        self._banner("AUTOFORGE")
        click.echo(f"  Idea: {idea}")
        click.echo(f"  Output: {self.config.output_dir}")
        click.echo(f"  Max iterations: {self.config.max_iterations}")

        # Phase 1: Interview
        self._banner("PHASE 1: INTERVIEW")
        interviewer = Interviewer(self.llm)
        spec = interviewer.run(idea)

        # Set up project directory
        project_dir = Path(self.config.output_dir) / spec.name
        project = Project(project_dir, timeout=self.config.subprocess_timeout)
        project.init(spec.name)

        # Save spec to project
        spec.save(project_dir)
        project.commit("Add project specification")
        click.echo(f"\n  Project: {spec.name}")
        click.echo(f"  Directory: {project_dir}")

        # Phase 2: Plan
        self._banner("PHASE 2: PLAN")
        planner = Planner(self.llm)
        plan = planner.generate(spec)
        plan.save(project_dir)
        project.commit("Add implementation plan")
        click.echo(f"  Generated {len(plan.steps)} steps")

        # Phase 3: Review
        if not self.config.skip_review:
            self._banner("PHASE 3: CARMACK REVIEW")
            reviewer = PlanReviewer(self.llm)
            plan, review = reviewer.review(plan, spec)
            plan.save(project_dir)
            project.commit("Plan reviewed and revised")
            click.echo(f"  Review: {review.summary}")
        else:
            click.echo("\n  Skipping plan review (--skip-review)")

        # Phase 4: Build
        self._banner("PHASE 4: BUILD")
        builder = Builder(self.llm, project, spec)
        failed_steps = builder.build(plan)
        if failed_steps:
            click.echo(f"\n  Warning: {len(failed_steps)} steps failed: {failed_steps}")
        else:
            click.echo("\n  All steps completed successfully")

        # Save updated plan
        plan.save(project_dir)

        # Phase 5: Refinement Loop
        self._banner("PHASE 5: REFINE")
        loop = ForgeLoop(
            llm=self.llm,
            project=project,
            spec=spec,
            max_iterations=self.config.max_iterations,
        )
        state = loop.run()

        # Final summary
        self._banner("COMPLETE")
        self._print_summary(spec, plan, state, project_dir)

    def resume(self, project_dir: str) -> None:
        """Resume a forge session from a checkpoint."""
        path = Path(project_dir)
        state_file = path / "forge_state.json"
        if not state_file.exists():
            click.echo(f"Error: No forge_state.json found in {project_dir}")
            return

        spec = ProjectSpec.load(path)
        state = ForgeState.load(state_file)
        project = Project(path, timeout=self.config.subprocess_timeout)

        self._banner("RESUMING AUTOFORGE")
        click.echo(f"  Project: {spec.name}")
        click.echo(f"  Resuming from iteration {state.iteration}")

        loop = ForgeLoop(
            llm=self.llm,
            project=project,
            spec=spec,
            max_iterations=self.config.max_iterations,
        )
        state = loop.run(state)

        from autoforge.planner import Plan
        plan = Plan.load(path)

        self._banner("COMPLETE")
        self._print_summary(spec, plan, state, path)

    def _banner(self, text: str) -> None:
        click.echo("\n" + "=" * 60)
        click.echo(f"  {text}")
        click.echo("=" * 60)

    def _print_summary(
        self,
        spec: ProjectSpec,
        plan: "Plan",
        state: ForgeState,
        project_dir: Path,
    ) -> None:
        completed_steps = sum(1 for s in plan.steps if s.done)
        total_steps = len(plan.steps)

        click.echo(f"  Project: {spec.name}")
        click.echo(f"  Directory: {project_dir}")
        click.echo(f"  Plan: {completed_steps}/{total_steps} steps completed")
        click.echo(f"  Refinement: {state.iteration} iterations")
        click.echo(f"  Result: {'SUCCESS' if state.success else 'INCOMPLETE'}")

        if state.skipped_criteria:
            click.echo(f"  Skipped criteria: {', '.join(state.skipped_criteria)}")

        click.echo(f"\n  Your app is ready at: {project_dir}")
