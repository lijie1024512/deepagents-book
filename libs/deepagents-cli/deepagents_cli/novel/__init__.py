"""Novel writing CLI module.

This module provides CLI commands for novel writing with deepagents.

Storage:
- SQLite (preferred): Uses NovelDatabase for ACID-compliant storage
- JSON/YAML (legacy): Falls back to file-based storage for old projects

Hooks System (inspired by planning-with-files):
- PreToolUse: Auto-read relevant context before write operations
- PostToolUse: Remind to update progress/check foreshadows after completion
- Auto-checkpoint: Create checkpoints after significant operations
- Session Recovery: 5-Question context reconstruction for interrupted sessions

Migration:
- Use `deepagents novel migrate` to convert old projects to SQLite
"""

from deepagents_cli.novel.commands import execute_novel_command, setup_novel_parser
from deepagents_cli.novel.database import NovelDatabase
from deepagents_cli.novel.hooks import (
    NovelHooksRegistry,
    build_hooks_system_prompt_section,
    get_session_recovery_context,
    init_hooks,
)
from deepagents_cli.novel.memory_middleware import NovelMemoryMiddleware, NovelSummarizationConfig
from deepagents_cli.novel.memory_tools import (
    add_relationship,
    complete_chapter,
    complete_outline,
    forget,
    get_all_memory_tools,
    get_character,
    get_memory_summary,
    get_novel_bootstrap_tools,
    get_progress,
    get_project_status,
    init_memory_store,
    init_novel_project,
    list_characters,
    list_foreshadows,
    plant_foreshadow,
    recall,
    remember,
    resolve_foreshadow,
    update_character,
    update_memory,
    update_progress,
)
from deepagents_cli.novel.migrate import (
    cleanup_old_files,
    get_migration_status,
    migrate_project,
    needs_migration,
    rollback_migration,
)
from deepagents_cli.novel.imitate_middleware import ImitateMemoryMiddleware
from deepagents_cli.novel.imitate_tools import get_all_imitate_tools, init_imitate_store
from deepagents_cli.novel.project import NovelProject

__all__ = [
    # Commands
    "setup_novel_parser",
    "execute_novel_command",
    # Project
    "NovelProject",
    # Database
    "NovelDatabase",
    # Migration
    "needs_migration",
    "migrate_project",
    "cleanup_old_files",
    "rollback_migration",
    "get_migration_status",
    # Hooks System
    "NovelHooksRegistry",
    "init_hooks",
    "get_session_recovery_context",
    "build_hooks_system_prompt_section",
    # Memory Middleware
    "NovelMemoryMiddleware",
    "NovelSummarizationConfig",
    # Project Tools
    "init_novel_project",
    "get_project_status",
    # Memory Tools
    "init_memory_store",
    "remember",
    "recall",
    "forget",
    "update_memory",
    # Character Tools
    "update_character",
    "get_character",
    "list_characters",
    "add_relationship",
    # Foreshadow Tools
    "plant_foreshadow",
    "resolve_foreshadow",
    "list_foreshadows",
    # Progress Tools
    "update_progress",
    "get_progress",
    # Chapter Completion Tools
    "complete_chapter",
    "complete_outline",
    # Helper functions
    "get_memory_summary",
    "get_all_memory_tools",
    "get_novel_bootstrap_tools",
    # Imitate module
    "ImitateMemoryMiddleware",
    "get_all_imitate_tools",
    "init_imitate_store",
]
