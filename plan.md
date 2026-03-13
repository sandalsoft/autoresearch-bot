# Implementation Plan: Autoforge

## Summary
Autoforge is a Python CLI tool that applies autoresearch's iterative methodology (plan, build, test, evaluate, repeat) to autonomous app development. Given an idea, it conducts a structured interview with the user, generates an implementation plan, runs a Carmack-level code review (using Claude Opus), builds the full app in one pass, then enters a refinement loop — running tests, executing user-defined tasks, judging results via LLM, and auto-reverting regressions. The loop caps at 10 iterations and stops early when all success criteria are met.

## Carmack Review Changes Applied
- Removed OpenAI Codex dependency — reviewer uses Claude Opus instead (single LLM provider)
- Removed GitPython — use subprocess git calls (simpler, no C extensions)
- Removed TOML config — CLI args + env vars only for v1
- Added dependency installation step for generated projects
- Added explicit Task schema for user-defined eval tasks
- Added failed-attempt memory to prevent revert loops
- Added subprocess timeouts (60s default)
- Added context management strategy for LLM calls
- Added syntax validation after code generation
- Builder validates each file after writing (py_compile, syntax check)
- Planner outputs explicit file tree

## Technical Stack
- **Language**: Python 3.12+
- **LLM**: Claude (Anthropic API) — Opus for planning/review, Sonnet for code gen, Haiku for evaluation
- **CLI Framework**: Click
- **Process Management**: subprocess for running generated apps/tests (with timeouts)
- **Git**: subprocess calls to `git` directly
- **Testing (Autoforge itself)**: pytest

## Phases

### Phase 1: Project Scaffolding
- [ ] Step 1.1: Create Python package structure — `autoforge/` package dir with `__init__.py`, `pyproject.toml` with Click + anthropic dependencies, and `.gitignore`
- [ ] Step 1.2: Create `autoforge/cli.py` — Click CLI entry point with the main `autoforge` group and a `forge` subcommand that accepts an `--idea` argument (or prompts interactively). Wire up in `pyproject.toml` as `[project.scripts] autoforge = "autoforge.cli:main"`
- [ ] Step 1.3: Create `autoforge/config.py` — `ForgeConfig` dataclass holding model IDs (three constants: PLAN_MODEL, CODE_MODEL, EVAL_MODEL), max iterations (default 10), subprocess timeout (default 60s), project output directory, API key from env var `ANTHROPIC_API_KEY`
- [ ] Step 1.4: Create `autoforge/llm.py` — LLM client wrapper around the Anthropic SDK. Functions: `chat(messages, model, system)`, `generate_code(prompt, model)`, `judge(criteria, result, model)`. Handles retries on transient errors, strips markdown fences from code responses, validates Python syntax via `py_compile`. Context management: summarizes large inputs, truncates test output to last 200 lines

### Phase 2: Interviewer & Spec
- [ ] Step 2.1: Create `autoforge/spec.py` — `ProjectSpec` dataclass with: project name, summary, language, framework, features list, file tree (list of planned paths), test command (e.g. "pytest"), and `eval_tasks: list[EvalTask]`. `EvalTask` dataclass has: name, command (shell command to run), success_criteria (text description for LLM judge). Includes `to_markdown()`, `to_json()`, `save(path)`, `load(path)` methods
- [ ] Step 2.2: Create `autoforge/interviewer.py` — `Interviewer` class that conducts structured CLI interview. Takes idea string, generates contextual questions using Claude Opus, asks one at a time via `click.prompt()`. Must ask: problem/audience, tech stack, features, what command runs tests, and at least one eval task (command + success criteria). Outputs a `ProjectSpec`

### Phase 3: Planner & Reviewer
- [ ] Step 3.1: Create `autoforge/planner.py` — `Planner` class that takes `ProjectSpec`, generates a step-by-step implementation plan using Claude Opus. Output is a `Plan` dataclass with ordered `PlanStep` objects (id, description, file_paths, acceptance_criteria) plus an explicit file_tree. Saves `plan.md` and `plan.json` in the generated project
- [ ] Step 3.2: Create `autoforge/reviewer.py` — `PlanReviewer` class using Claude Opus for Carmack-level review. Identifies: architectural flaws, missing edge cases, over-engineering, security concerns, dependency risks. Returns `ReviewResult` with issues and suggested fixes. If critical issues found, auto-revises the plan (max 2 rounds). No OpenAI dependency

### Phase 4: Builder
- [ ] Step 4.1: Create `autoforge/project.py` — `Project` class managing the generated project directory. Methods: `init(path, name)` creates directory + `git init`, `commit(message)` stages all + commits, `revert()` does `git revert HEAD --no-edit`, `get_diff()` returns diff, `install_deps()` detects requirements.txt/package.json and installs dependencies in the project. All git ops via `subprocess.run(["git", ...], cwd=self.path, timeout=30)`
- [ ] Step 4.2: Create `autoforge/builder.py` — `Builder` class that iterates plan steps, generates code via Claude Sonnet, writes files, validates syntax (py_compile for .py files), and commits each step. After all steps: calls `project.install_deps()`. Context management: sends only the current step + file tree + contents of files being modified (not the whole project)

### Phase 5: Test Runner & Evaluator
- [ ] Step 5.1: Create `autoforge/runner.py` — `TestRunner` class. `run_tests(project, test_cmd)` runs the test command via subprocess with configurable timeout, returns `TestResult` (passed: bool, output: str, num_passed, num_failed). `run_task(project, task: EvalTask)` runs the task command, captures stdout/stderr, returns `TaskResult` (task_name, output, exit_code). All subprocess calls use timeout from config
- [ ] Step 5.2: Create `autoforge/evaluator.py` — `Evaluator` class. Takes `TestResult` + list of `TaskResult`, judges against `ProjectSpec.eval_tasks` criteria using Claude Haiku. Returns `EvalResult` with per-criteria pass/fail + reasoning, overall verdict, and suggested improvements. Truncates task output to last 200 lines before sending to LLM

### Phase 6: Refinement Loop
- [ ] Step 6.1: Create `autoforge/refiner.py` — `Refiner` class that takes `EvalResult`, current project source, and a `failed_attempts: list[str]` memory of what was tried before. Generates targeted fixes via Claude Sonnet, applies them. The failed_attempts list is included in the prompt so Claude doesn't repeat the same fix
- [ ] Step 6.2: Create `autoforge/loop.py` — `ForgeLoop` class orchestrating the cycle. Logic: run tests → if tests fail, that's the focus → evaluate tasks → if all pass + all criteria met, stop (success) → else refine → commit → re-run tests → if regression (something that passed now fails), revert + add to failed_attempts → if same issue regresses 3 times, skip it → repeat up to max_iterations. Tracks `IterationLog` per cycle. Emits CLI output per iteration. Checkpoints state to `forge_state.json` after each iteration

### Phase 7: Pipeline Orchestration
- [ ] Step 7.1: Create `autoforge/pipeline.py` — `ForgePipeline` wiring full lifecycle: Interview → Plan → Review → Build → Loop. Each phase prints a clear banner. Handles errors gracefully (if review fails, continue with unreviewed plan; if build step fails, continue to next step). Saves all artifacts to project directory
- [ ] Step 7.2: Wire up `autoforge/cli.py` — Connect `forge` command to `ForgePipeline.run()`. Flags: `--output-dir` (default `./output`), `--max-iterations` (default 10), `--skip-review`, `--verbose`, `--timeout` (subprocess timeout, default 60). Add `resume` subcommand that reads `forge_state.json` to continue from last checkpoint

### Phase 8: Testing & Validation
- [ ] Step 8.1: Create `tests/test_config.py` — Unit tests for ForgeConfig defaults and env var loading
- [ ] Step 8.2: Create `tests/test_spec.py` — Unit tests for ProjectSpec and EvalTask serialization (to_markdown, to_json, save/load roundtrip)
- [ ] Step 8.3: Create `tests/test_loop.py` — Unit tests for ForgeLoop: stops on success, reverts on regression, caps at max iterations, skips after 3 strikes on same issue. All LLM calls mocked with fixture responses
- [ ] Step 8.4: Create `tests/test_pipeline.py` — Integration test with mocked LLM verifying full flow executes and produces expected artifacts
- [ ] Step 8.5: End-to-end smoke test — Verify CLI starts, prompts for idea, and basic argument parsing works
