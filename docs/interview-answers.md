# Autoforge — Project Discovery Interview

## Project Name
**Autoforge**

## Summary
Autoforge is a Python CLI tool that applies the autoresearch methodology (plan, build, test, evaluate, repeat) to autonomous app development instead of ML model training. Given an idea, it interviews the user to understand requirements, generates an implementation plan, runs a Carmack-level code review via Codex, builds the full app, then enters an iterative refinement loop — running tests, executing user-defined tasks, and using an LLM to judge results against success criteria. It auto-reverts regressions, stops when "good enough," and caps at 10 refinement cycles.

## Technical Decisions

| Decision | Choice |
|----------|--------|
| Language | Python |
| LLM Provider | Claude (Anthropic API) |
| Model Selection | Auto-select per task (e.g., Haiku for quick evals, Sonnet/Opus for planning and code gen) |
| Interface | CLI |
| Code Review | Codex-powered Carmack-level review after planning |
| Generated Project Structure | New git repo per project |
| Execution Environment | Local (v1), Docker planned for v2 |

## Feature List

### Must-Have (v1)
1. **Interview-based idea intake** — Structured discovery interview (flow-next-interview pattern) to flesh out the idea from the user
2. **Plan generation** — Implementation plan from interview answers (flow-next-plan pattern)
3. **Carmack-level review** — Codex-powered deep review of the plan for flaws, edge cases, over-engineering before building
4. **Full initial build** — Execute the entire plan, generating the complete app in one pass
5. **Automated test + LLM eval loop** — Up to 10 refinement cycles:
   - Run tests (unit, integration, etc.)
   - Execute user-defined tasks against the running app
   - LLM judges task results against user-defined success criteria
   - Success criteria optionally refined by LLM
6. **Auto-revert on regressions** — If a refinement breaks previously passing tests, revert automatically
7. **Early stopping** — Stop the loop when all tests pass and eval criteria are met ("good enough")
8. **Auto-select Claude model** — Pick the appropriate Claude model for each task type
9. **Git integration** — New repo per project, commits at each step (build, each refinement cycle)

### Out of Scope (v1)
- Web UI
- Multi-user support
- Cloud deployment
- Docker containerization (planned for v2)
- Parallel experiments

## Architecture Decisions

### Core Loop (mirrors autoresearch)
```
Interview → Plan → Carmack Review → Build → [Test → Evaluate → Refine] × 10 max → Done
```

### Key Components
1. **Interviewer** — Conducts structured discovery interview with the user, writes answers to a spec file
2. **Planner** — Generates implementation plan from interview answers
3. **Reviewer** — Codex-powered Carmack-level review of the plan
4. **Builder** — Executes the plan, generating the full app (code, tests, config)
5. **Test Runner** — Executes tests and user-defined tasks against the app
6. **Evaluator** — LLM judges task results against success criteria
7. **Refiner** — Proposes and applies fixes based on evaluation feedback
8. **Loop Controller** — Orchestrates the test/evaluate/refine cycle, handles revert logic, tracks iteration count, checks early stopping

### Evaluation Framework
- **Hard gate**: All tests must pass
- **Qualitative gate**: User-defined tasks are executed and judged by an LLM against user-defined success criteria
- **Revert policy**: If a refinement causes regressions (previously passing tests now fail), auto-revert to last good state
- **Stop conditions**: All tests pass AND all eval criteria met, OR 10 iterations reached

## Constraints & Requirements
- Python 3.12+
- Anthropic Python SDK for Claude API access
- CLI-only interface for v1
- Each generated project gets its own git repository
- Local execution of generated apps (no sandboxing in v1)
- Model auto-selection: use cheaper/faster models for quick tasks, more capable models for complex reasoning

## Definition of Done
v1 is complete when:
- A user can provide an idea via CLI
- The system interviews them, generates a plan, reviews it, builds the app, and iteratively refines it
- The generated app lives in its own git repo with meaningful commit history
- The refinement loop correctly reverts regressions and stops when criteria are met or 10 iterations pass
- The full lifecycle runs end-to-end without manual intervention (after the initial interview)
