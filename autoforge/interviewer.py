"""Structured discovery interview for gathering project requirements."""

from __future__ import annotations

import json

import click

from autoforge.config import PLAN_MODEL
from autoforge.llm import LLMClient
from autoforge.spec import EvalTask, ProjectSpec


INTERVIEW_SYSTEM = """You are an expert software architect conducting a discovery interview \
to understand a project idea deeply before building it. You generate thoughtful, contextual \
questions one at a time. Your goal is to gather enough information to write a complete \
project specification.

You must gather:
1. Project name
2. Core problem and audience
3. Programming language and framework preferences
4. 3-5 must-have features for v1
5. Key data entities and architecture
6. What command runs the tests (e.g., pytest, npm test)
7. At least one evaluation task: a shell command to run against the app and the criteria for success
8. Any constraints or preferences

Be conversational, not robotic. Build on previous answers. Aim for 6-10 questions total."""


SPEC_EXTRACTION_PROMPT = """Based on the following interview transcript, extract a complete \
project specification as JSON. The JSON must have this exact structure:

{{
    "name": "project-name",
    "summary": "one paragraph summary",
    "language": "python",
    "framework": "framework or 'none'",
    "features": ["feature 1", "feature 2"],
    "file_tree": ["src/main.py", "src/models.py", "tests/test_main.py"],
    "test_command": "pytest",
    "eval_tasks": [
        {{
            "name": "task name",
            "command": "shell command to run",
            "success_criteria": "what success looks like"
        }}
    ],
    "architecture_notes": "architecture decisions",
    "constraints": "constraints and requirements"
}}

IMPORTANT: The file_tree should be a reasonable set of files for the project. \
The eval_tasks must have at least one task with a concrete command and success criteria.

## Interview Transcript
{transcript}

Respond with ONLY the JSON, no markdown fences or extra text."""


class Interviewer:
    """Conducts a structured discovery interview via CLI."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.transcript: list[dict[str, str]] = []

    def run(self, idea: str) -> ProjectSpec:
        """Run the full interview and return a ProjectSpec."""
        click.echo("\n" + "=" * 60)
        click.echo("  AUTOFORGE — Project Discovery Interview")
        click.echo("=" * 60)
        click.echo(f"\nIdea: {idea}\n")

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"The user wants to build: {idea}\n\n"
                    "Generate your first interview question. Ask ONE question at a time. "
                    "Respond with ONLY the question, nothing else."
                ),
            }
        ]

        question_count = 0
        max_questions = 10

        while question_count < max_questions:
            # Get question from Claude
            question = self.llm.chat(
                messages=messages,
                model=PLAN_MODEL,
                system=INTERVIEW_SYSTEM,
            )

            # Ask user
            click.echo(f"\n[Q{question_count + 1}] {question}")
            answer = click.prompt("\nYour answer", type=str)

            self.transcript.append({"question": question, "answer": answer})
            question_count += 1

            # Check if we should continue
            messages.append({"role": "assistant", "content": question})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"User's answer: {answer}\n\n"
                        f"You've asked {question_count} questions so far. "
                        f"{'You should wrap up soon. ' if question_count >= 6 else ''}"
                        "If you have enough information to write a complete spec "
                        "(including project name, language, features, test command, "
                        "and at least one eval task), respond with exactly 'INTERVIEW_COMPLETE'. "
                        "Otherwise, ask your next question. Respond with ONLY the question or "
                        "'INTERVIEW_COMPLETE'."
                    ),
                }
            )

            # Check response
            response = self.llm.chat(
                messages=messages,
                model=PLAN_MODEL,
                system=INTERVIEW_SYSTEM,
            )

            if "INTERVIEW_COMPLETE" in response:
                click.echo("\nInterview complete. Generating project specification...")
                break

            # Continue with next question
            messages.append({"role": "assistant", "content": response})

        return self._extract_spec()

    def _extract_spec(self) -> ProjectSpec:
        """Extract a ProjectSpec from the interview transcript."""
        transcript_text = ""
        for entry in self.transcript:
            transcript_text += f"Q: {entry['question']}\nA: {entry['answer']}\n\n"

        prompt = SPEC_EXTRACTION_PROMPT.format(transcript=transcript_text)

        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=PLAN_MODEL,
            max_tokens=4096,
        )

        # Parse JSON from response (handle possible markdown fences)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        data = json.loads(raw)
        return ProjectSpec.from_dict(data)
