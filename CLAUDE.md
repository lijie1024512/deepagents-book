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

## Build & Development Commands

Uses `uv` package manager. All commands run from within each library directory.

### deepagents (libs/deepagents/)

```bash
make lint           # Format check + linting + mypy
make format         # Auto-format with ruff
make test           # Unit tests with coverage
make integration_test  # Integration tests (requires API keys)
```

### deepagents-cli (libs/deepagents-cli/)

```bash
make lint           # Ruff format check + linting
make format         # Auto-format
make test           # Unit tests (sockets disabled)
make test_integration  # Integration tests
make test_watch     # Watch mode
uv run deepagents   # Run CLI locally
```

### Running a single test

```bash
cd libs/deepagents && uv run pytest tests/unit_tests/test_middleware.py -k "test_name"
cd libs/deepagents-cli && uv run pytest tests/unit_tests/test_cli.py::test_function
```

### Install dependencies

```bash
uv sync --all-groups
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

## Code Style

- **Python**: 3.11+ required
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
- wcmatch (glob pattern matching)
- textual, prompt-toolkit, rich (CLI TUI)
- Default model: claude-sonnet-4-5-20250929

## Testing Notes

- Unit tests disable network with `--disable-socket`
- Integration tests require `ANTHROPIC_API_KEY` or other provider keys
- Tests use pytest-cov for coverage reporting
