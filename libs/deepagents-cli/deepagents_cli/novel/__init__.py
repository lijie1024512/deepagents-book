"""Novel writing CLI module.

This module provides CLI commands for novel writing with deepagents.
"""

from deepagents_cli.novel.commands import execute_novel_command, setup_novel_parser
from deepagents_cli.novel.memory_middleware import NovelMemoryMiddleware, NovelSummarizationConfig
from deepagents_cli.novel.memory_tools import (
    add_relationship,
    complete_chapter,
    complete_outline,
    forget,
    get_all_memory_tools,
    get_character,
    get_memory_summary,
    get_progress,
    init_memory_store,
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
from deepagents_cli.novel.project import NovelProject

__all__ = [
    # Commands
    "setup_novel_parser",
    "execute_novel_command",
    # Project
    "NovelProject",
    # Memory Middleware
    "NovelMemoryMiddleware",
    "NovelSummarizationConfig",
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
]
