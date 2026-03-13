"""CLI entry point for Autoforge."""

from __future__ import annotations

import click

from autoforge.config import ForgeConfig


@click.group()
@click.version_option(package_name="autoforge")
def main() -> None:
    """Autoforge — autonomous app builder."""


@main.command()
@click.option("--idea", "-i", prompt="What do you want to build?", help="App idea description")
@click.option("--output-dir", "-o", default="./output", help="Output directory for generated projects")
@click.option("--max-iterations", "-n", default=10, help="Max refinement loop iterations")
@click.option("--skip-review", is_flag=True, help="Skip the Carmack-level plan review")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--timeout", "-t", default=60, help="Subprocess timeout in seconds")
def forge(
    idea: str,
    output_dir: str,
    max_iterations: int,
    skip_review: bool,
    verbose: bool,
    timeout: int,
) -> None:
    """Build an app from an idea using the plan/build/test/evaluate/repeat loop."""
    config = ForgeConfig(
        output_dir=output_dir,
        max_iterations=max_iterations,
        subprocess_timeout=timeout,
        verbose=verbose,
        skip_review=skip_review,
    )
    config.validate()

    from autoforge.pipeline import ForgePipeline

    pipeline = ForgePipeline(config)
    pipeline.run(idea)


@main.command()
@click.argument("project_dir")
def resume(project_dir: str) -> None:
    """Resume a forge session from a checkpoint."""
    from autoforge.pipeline import ForgePipeline

    config = ForgeConfig()
    config.validate()
    pipeline = ForgePipeline(config)
    pipeline.resume(project_dir)
