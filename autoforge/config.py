"""Configuration for Autoforge."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


PLAN_MODEL = "claude-opus-4-20250514"
CODE_MODEL = "claude-sonnet-4-20250514"
EVAL_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class ForgeConfig:
    """Runtime configuration for a forge session."""

    output_dir: str = "./output"
    max_iterations: int = 10
    subprocess_timeout: int = 60
    verbose: bool = False
    skip_review: bool = False
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Set it with: export ANTHROPIC_API_KEY=your-key"
            )
