"""LLM client wrapper around the Anthropic SDK."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import anthropic

from autoforge.config import CODE_MODEL, EVAL_MODEL, PLAN_MODEL, ForgeConfig


class LLMClient:
    """Wrapper around the Anthropic API with retry logic and response parsing."""

    def __init__(self, config: ForgeConfig) -> None:
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.api_key)

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 16384,
    ) -> str:
        """Send a chat request and return the text response."""
        model = model or PLAN_MODEL
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        for attempt in range(3):
            try:
                response = self.client.messages.create(**kwargs)
                return response.content[0].text
            except anthropic.RateLimitError:
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise
            except anthropic.APIStatusError as e:
                if e.status_code >= 500 and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise

    def generate_code(self, prompt: str, model: str | None = None) -> str:
        """Generate code and return it with markdown fences stripped."""
        model = model or CODE_MODEL
        raw = self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        return strip_markdown_fences(raw)

    def judge(self, criteria: str, result: str, model: str | None = None) -> str:
        """Judge a result against criteria. Returns the LLM's assessment."""
        model = model or EVAL_MODEL
        prompt = (
            "You are an evaluator. Judge the following result against the success criteria.\n\n"
            f"## Success Criteria\n{criteria}\n\n"
            f"## Actual Result\n{truncate_output(result)}\n\n"
            "Respond with a JSON object: "
            '{"passed": true/false, "reasoning": "...", "suggestions": ["..."]}'
        )
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=2048,
        )

    def plan(self, prompt: str) -> str:
        """Generate a plan using the planning model."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=PLAN_MODEL,
        )

    def review(self, prompt: str) -> str:
        """Review code/plan using the planning model."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=PLAN_MODEL,
        )


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    # Match ```lang\n...\n``` blocks
    pattern = r"```[\w]*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return "\n".join(matches)
    return text


def truncate_output(text: str, max_lines: int = 200) -> str:
    """Truncate output to the last N lines."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return f"... (truncated {len(lines) - max_lines} lines) ...\n" + "\n".join(
        lines[-max_lines:]
    )


def validate_python_syntax(code: str) -> tuple[bool, str]:
    """Validate Python syntax by attempting to compile it. Returns (valid, error_msg)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", f.name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Syntax check timed out"
        finally:
            Path(f.name).unlink(missing_ok=True)
