# Autoforge

Autonomous app builder that applies the [autoresearch](https://github.com/karpathy/autoresearch) methodology — **plan, build, test, evaluate, repeat** — to building software instead of training models.

Give it an idea. It interviews you, generates a plan, reviews it, builds the app, then iteratively tests and refines it until it works.

## How It Works

```
Interview → Plan → Carmack Review → Build → [Test → Evaluate → Refine] × 10 → Done
```

1. **Interview** — Structured discovery interview gathers requirements, tech stack, features, and success criteria
2. **Plan** — Generates a step-by-step implementation plan from the interview
3. **Review** — Carmack-level code review of the plan using Claude Opus, with auto-revision for critical issues
4. **Build** — Executes the full plan, generating the complete app in one pass
5. **Refine** — Iterative loop (up to 10 cycles):
   - Runs tests (hard gate — must pass)
   - Executes user-defined evaluation tasks
   - LLM judges results against success criteria
   - Auto-reverts regressions
   - Stops early when "good enough"

Each generated project gets its own git repo with meaningful commit history.

## Quickstart

```bash
# Install
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY=your-key-here

# Build an app
autoforge forge --idea "a CLI tool that converts CSV files to JSON"
```

Autoforge will interview you, then autonomously build, test, and refine the app.

## Getting Started

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)

### Installation

```bash
git clone https://github.com/sandalsoft/autoresearch-bot.git
cd autoresearch-bot
pip install -e .
```

### Usage

**Build a new app:**

```bash
autoforge forge --idea "a URL shortener with click tracking"
```

**Customize the run:**

```bash
autoforge forge \
  --idea "a REST API for managing bookmarks" \
  --output-dir ./projects \
  --max-iterations 5 \
  --timeout 120 \
  --skip-review
```

**Resume from a checkpoint** (if a run was interrupted):

```bash
autoforge resume ./output/my-project
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--idea`, `-i` | *(prompted)* | App idea description |
| `--output-dir`, `-o` | `./output` | Where generated projects are created |
| `--max-iterations`, `-n` | `10` | Max refinement loop iterations |
| `--skip-review` | `false` | Skip the Carmack-level plan review |
| `--verbose`, `-v` | `false` | Verbose output |
| `--timeout`, `-t` | `60` | Subprocess timeout in seconds |

## Architecture

```
autoforge/
├── cli.py           # Click CLI entry point
├── config.py        # Configuration and model constants
├── llm.py           # Anthropic SDK wrapper with retry and parsing
├── interviewer.py   # Structured discovery interview
├── spec.py          # ProjectSpec and EvalTask data models
├── planner.py       # Plan generation from spec
├── reviewer.py      # Carmack-level plan review
├── project.py       # Git operations for generated projects
├── builder.py       # Code generation with syntax validation
├── runner.py        # Test and task execution with timeouts
├── evaluator.py     # LLM-judged evaluation against criteria
├── refiner.py       # Targeted code fixes with failed-attempt memory
├── loop.py          # Refinement loop with revert and checkpointing
└── pipeline.py      # Full lifecycle orchestration
```

### Key Design Decisions

- **Single LLM provider** — Claude only (Opus for planning/review, Sonnet for code gen, Haiku for evaluation). No OpenAI dependency.
- **Subprocess git** — Direct `git` calls instead of GitPython. Simpler, fewer dependencies.
- **Failed-attempt memory** — The refiner tracks what was tried before to avoid repeating the same fix.
- **3-strike skip** — If the same criteria regresses 3 times, it's skipped to avoid burning tokens.
- **State checkpointing** — `forge_state.json` saved after each iteration for resume support.

### Evaluation Framework

- **Hard gate**: All tests must pass (test command defined during interview)
- **Qualitative gate**: User-defined tasks are executed and judged by an LLM against success criteria
- **Revert policy**: If a refinement breaks previously passing tests, auto-revert
- **Stop conditions**: All criteria met, or max iterations reached

## Inspired By

[autoresearch](https://github.com/karpathy/autoresearch) by Andrej Karpathy — autonomous ML experiment runner that modifies `train.py`, runs training, evaluates results, and iterates. Autoforge applies the same loop to building entire applications.

## License

MIT
