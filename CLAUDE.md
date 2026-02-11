# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Deep Agents is an open-source agent framework built on LangGraph that implements long-horizon task execution patterns (planning, filesystem access, subagent delegation, memory management). The project is a Python monorepo with multiple libraries.

## Repository Structure

```
deepagents-book/
├── libs/
│   ├── deepagents/           # Core framework (v0.3.7) - create_deep_agent()
│   ├── deepagents-cli/       # Terminal CLI application (v0.0.13a2)
│   ├── harbor/               # Evaluation framework for Terminal Bench 2.0
│   └── acp/                  # Agent Client Protocol (WIP)
├── examples/                 # Example agents and use cases
└── novels/                   # Novel generation examples
```

## Toolchain Preferences

- **Backend (Python)**: prefer `uv` for dependency installation and project startup (`uv sync`, `uv run`)
- **Frontend (JS/TS)**: prefer `pnpm` for dependency installation and project startup (`pnpm install`, `pnpm dev`)
- **Data modeling (Python)**: prefer `pydantic` for data validation, serialization, and config models

## Build & Development Commands

Uses `uv` package manager. All commands run from within each library directory.

### deepagents (libs/deepagents/)

```bash
uv sync --all-groups   # Install dependencies
make lint              # Format check + linting + mypy
make format            # Auto-format with ruff
make test              # Unit tests with coverage
make integration_test  # Integration tests (requires API keys)
```

### deepagents-cli (libs/deepagents-cli/)

```bash
uv sync --all-groups   # Install dependencies
make lint              # Ruff format check + linting
make format            # Auto-format
make test              # Unit tests (sockets disabled)
make test_integration  # Integration tests
make test_watch        # Watch mode
uv run deepagents      # Run CLI locally
```

### Running a single test

```bash
cd libs/deepagents && uv run pytest tests/unit_tests/test_middleware.py -k "test_name"
cd libs/deepagents-cli && uv run pytest tests/unit_tests/test_cli.py::test_function
```

## Architecture

### Core Framework (deepagents)

The main entry point is `create_deep_agent()` in `libs/deepagents/deepagents/graph.py`, which returns a compiled LangGraph `StateGraph`.

**Middleware pattern**: Tools and capabilities are injected via middleware classes that add tools and system prompt instructions:
- `TodoListMiddleware` - write_todos, read_todos
- `FilesystemMiddleware` - ls, read_file, write_file, edit_file, glob, grep, execute
- `SubAgentMiddleware` - task() for spawning isolated subagents
- `SummarizationMiddleware` - auto-summarizes when context > 170k tokens
- `MemoryMiddleware`, `SkillsMiddleware` - optional persistent state

**Backend protocol**: Pluggable storage backends in `libs/deepagents/deepagents/backends/`:
- `StateBackend` (default) - ephemeral in-memory
- `FilesystemBackend` - real disk operations
- `StoreBackend` - LangGraph Store (persistent)
- `CompositeBackend` - route different paths to different backends

### CLI (deepagents-cli)

Entry point: `libs/deepagents-cli/deepagents_cli/main.py::cli_main()`

Key modules:
- `agent.py` - Agent configuration and execution
- `tools.py` - Tool implementations
- `skills/` - Skill loading and progressive disclosure
- `integrations/` - Sandbox integrations (Modal, Daytona, Runloop)
- `textual_app/` - TUI implementation

### Novel Writing Agent — Phased Skill Architecture

The novel agent uses a **phase-based skill injection** system instead of loading all skills at once.

**6 phases** (sequential flow):
`brainstorm` → `engine` → `character` → `outline` → `writing` → `revision`

**Skill structure**:
```
skills/
├── novel-orchestrator/SKILL.md              # Always loaded — phase table + transition rules
├── novel-phase-brainstorm/SKILL.md          # Phase 1: type + appeal selection
├── novel-phase-engine/SKILL.md              # Phase 2: creative engine design (3+ proposals)
│   └── references/creative_hooks_summary.md
├── novel-phase-character/SKILL.md           # Phase 3: character from engine
├── novel-phase-outline/SKILL.md             # Phase 4: arc planning, rolling 5-10 chapters
│   └── references/outline_structure_summary.md
├── novel-phase-writing/SKILL.md             # Phase 5: multi-version chapters, scene-by-scene
└── novel-phase-revision/SKILL.md            # Phase 6: multi-dimension diagnosis
```

**Key components**:
- `novel/database.py` — SQLite with `current_phase` and `phase_completed` in progress table
- `novel/project.py` — `NovelState` dataclass with phase tracking fields
- `novel/memory_tools.py` — `advance_phase()` tool with precondition checks, skip/back support
- `novel/memory_middleware.py` — `NovelMemoryMiddleware` loads orchestrator + current phase skill on each model call (cached)
- `novel/hooks.py` — `NovelHooksRegistry` for automatic context management and session recovery

**Phase transition**: agent calls `advance_phase("engine", "用户确认了类型和吸引力")` to move forward. Preconditions are checked, decisions logged to memory, and the middleware auto-switches to the next phase's skill.

## Code Style

- **Python**: 3.11+ required, prefer pydantic for data models
- **Line length**: 150 (deepagents), 100 (deepagents-cli)
- **Formatter/Linter**: ruff with ALL rules enabled
- **Type checking**: mypy strict mode
- **Docstrings**: Google style
- **Async testing**: pytest-asyncio with `asyncio_mode = "auto"`

## Commit Conventions

Uses Conventional Commits format enforced by CI:
- Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert, release
- Scopes: deepagents, deepagents-cli, harbor, acp, examples, infra, deps

## Key Dependencies

- langchain-core, langchain, langchain-anthropic, langchain-google-genai
- pydantic (data validation and modeling)
- wcmatch (glob pattern matching)
- textual, prompt-toolkit, rich (CLI TUI)
- Default model: claude-sonnet-4-5-20250929

## Testing Notes

- Unit tests disable network with `--disable-socket`
- Integration tests require `ANTHROPIC_API_KEY` or other provider keys
- Tests use pytest-cov for coverage reporting
