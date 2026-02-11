"""Skill loader for CLI commands.

This module provides filesystem-based skill loading for CLI operations (list, create, info).
It wraps the prebuilt middleware functionality from deepagents.middleware.skills and adapts
it for direct filesystem access needed by CLI commands.

For middleware usage within agents, use deepagents.middleware.skills.SkillsMiddleware directly.
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import SkillMetadata, _list_skills as list_skills_from_backend


class ExtendedSkillMetadata(SkillMetadata):
    """Extended skill metadata for CLI display, adds source tracking."""

    source: str


# Re-export for CLI commands
__all__ = ["SkillMetadata", "list_skills"]


def list_skills(
    *,
    user_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    builtin_skills_dir: Path | None = None,
) -> list[ExtendedSkillMetadata]:
    """List skills from builtin, user and/or project directories.

    This is a CLI-specific wrapper around the prebuilt middleware's skill loading
    functionality. It uses FilesystemBackend to load skills from local directories.

    Priority order (later overrides earlier):
    1. builtin skills (shipped with deepagents-cli)
    2. user skills ({project_root}/.deepagents/{agent}/skills/)
    3. project skills ({project}/.deepagents/skills/)

    Args:
        user_skills_dir: Path to the user-level skills directory.
        project_skills_dir: Path to the project-level skills directory.
        builtin_skills_dir: Path to the built-in skills directory (deepagents_cli/skills).

    Returns:
        Merged list of skill metadata from all sources, with project skills
        taking precedence over user skills, and user over builtin.
    """
    all_skills: dict[str, ExtendedSkillMetadata] = {}

    # Load builtin skills first (lowest priority)
    if builtin_skills_dir and builtin_skills_dir.exists():
        builtin_backend = FilesystemBackend(root_dir=str(builtin_skills_dir))
        builtin_skills = list_skills_from_backend(backend=builtin_backend, source_path=".")
        for skill in builtin_skills:
            extended_skill: ExtendedSkillMetadata = {**skill, "source": "builtin"}
            all_skills[skill["name"]] = extended_skill

    # Load user skills second
    if user_skills_dir and user_skills_dir.exists():
        user_backend = FilesystemBackend(root_dir=str(user_skills_dir))
        user_skills = list_skills_from_backend(backend=user_backend, source_path=".")
        for skill in user_skills:
            # Add source field for CLI display
            extended_skill: ExtendedSkillMetadata = {**skill, "source": "user"}
            all_skills[skill["name"]] = extended_skill

    # Load project skills last (highest priority, override/augment)
    if project_skills_dir and project_skills_dir.exists():
        project_backend = FilesystemBackend(root_dir=str(project_skills_dir))
        project_skills = list_skills_from_backend(backend=project_backend, source_path=".")
        for skill in project_skills:
            # Add source field for CLI display
            extended_skill: ExtendedSkillMetadata = {**skill, "source": "project"}
            all_skills[skill["name"]] = extended_skill

    return list(all_skills.values())
