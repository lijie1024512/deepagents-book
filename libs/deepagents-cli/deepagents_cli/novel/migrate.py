"""Migration tools for novel projects.

This module provides migration utilities to convert existing YAML/JSON-based
novel projects to the new SQLite-based storage format.

Migration process:
1. Detect if project uses old format (state.yaml, memory.json)
2. Create new SQLite database
3. Import data from old files
4. Backup old files with .bak extension
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from deepagents_cli.novel.database import NovelDatabase


def needs_migration(project_path: Path) -> bool:
    """Check if a project needs migration to SQLite.

    Args:
        project_path: Path to the novel project

    Returns:
        True if project uses old format and needs migration
    """
    novel_dir = project_path / ".novel"
    db_file = novel_dir / "novel.db"
    state_file = novel_dir / "state.yaml"
    memory_file = novel_dir / "memory" / "memory.json"

    # If DB exists, no migration needed
    if db_file.exists():
        return False

    # If old files exist, migration needed
    return state_file.exists() or memory_file.exists()


def migrate_project(project_path: Path, backup: bool = True) -> dict[str, Any]:
    """Migrate a project from YAML/JSON to SQLite.

    Args:
        project_path: Path to the novel project
        backup: Whether to backup old files (default: True)

    Returns:
        Migration result dict with:
        - success: bool
        - migrated_files: list of migrated file names
        - backed_up_files: list of backed up file names
        - errors: list of error messages
    """
    result: dict[str, Any] = {
        "success": False,
        "migrated_files": [],
        "backed_up_files": [],
        "errors": [],
    }

    novel_dir = project_path / ".novel"
    state_file = novel_dir / "state.yaml"
    memory_file = novel_dir / "memory" / "memory.json"
    checkpoints_dir = novel_dir / "checkpoints"

    # Check if already migrated
    if (novel_dir / "novel.db").exists():
        result["errors"].append("Project already has a SQLite database. Skipping migration.")
        return result

    try:
        # Create new database
        db = NovelDatabase(project_path)

        # Migrate state.yaml
        if state_file.exists():
            try:
                state_data = yaml.safe_load(state_file.read_text(encoding="utf-8")) or {}
                _migrate_state(db, state_data)
                result["migrated_files"].append("state.yaml")

                if backup:
                    backup_path = state_file.with_suffix(".yaml.bak")
                    shutil.copy2(state_file, backup_path)
                    result["backed_up_files"].append(str(backup_path))
            except Exception as e:
                result["errors"].append(f"Error migrating state.yaml: {e}")

        # Migrate memory.json
        if memory_file.exists():
            try:
                memory_data = json.loads(memory_file.read_text(encoding="utf-8")) or {}
                _migrate_memory(db, memory_data)
                result["migrated_files"].append("memory.json")

                if backup:
                    backup_path = memory_file.with_suffix(".json.bak")
                    shutil.copy2(memory_file, backup_path)
                    result["backed_up_files"].append(str(backup_path))
            except Exception as e:
                result["errors"].append(f"Error migrating memory.json: {e}")

        # Migrate old checkpoints (if any)
        if checkpoints_dir.exists():
            try:
                migrated_count = _migrate_checkpoints(db, checkpoints_dir)
                if migrated_count > 0:
                    result["migrated_files"].append(f"checkpoints ({migrated_count} files)")

                    if backup:
                        backup_dir = checkpoints_dir.with_name("checkpoints.bak")
                        if not backup_dir.exists():
                            shutil.copytree(checkpoints_dir, backup_dir)
                            result["backed_up_files"].append(str(backup_dir))
            except Exception as e:
                result["errors"].append(f"Error migrating checkpoints: {e}")

        # Create initial checkpoint after migration
        db.create_checkpoint("migration_complete")

        result["success"] = len(result["errors"]) == 0

    except Exception as e:
        result["errors"].append(f"Migration failed: {e}")

    return result


def _migrate_state(db: NovelDatabase, state_data: dict[str, Any]) -> None:
    """Migrate state.yaml data to database.

    Args:
        db: NovelDatabase instance
        state_data: Parsed state.yaml data
    """
    # Migrate progress
    if "progress" in state_data:
        progress = state_data["progress"]
        outline = progress.get("outline", {})
        writing = progress.get("writing", {})

        db.update_progress(
            outline_total=outline.get("total", 0),
            outline_completed=outline.get("completed", 0),
            writing_total=writing.get("total", 0),
            writing_completed=writing.get("completed", 0),
            current_chapter=writing.get("current", 1),
        )

    # Migrate characters
    if "characters" in state_data:
        for name, char_data in state_data["characters"].items():
            db.update_character(
                name=name,
                location=char_data.get("location", "未知"),
                status=char_data.get("status", "未出场"),
                power_level=char_data.get("power_level", "未知"),
                relationships=char_data.get("relationships", {}),
                last_appearance=char_data.get("last_appearance", 0),
                notes=char_data.get("notes", ""),
            )

    # Migrate foreshadowing
    if "foreshadowing" in state_data:
        for f in state_data["foreshadowing"]:
            name = f.get("name", f.get("content", "")[:20])
            db.plant_foreshadow(
                name=name,
                content=f.get("content", ""),
                chapter=f.get("chapter"),
                target_chapter=f.get("target_chapter"),
            )
            if f.get("resolved", False):
                db.resolve_foreshadow(
                    name=name,
                    resolved_chapter=f.get("resolved_chapter", 0),
                    resolution=f.get("resolution"),
                )

    # Migrate butterfly effects
    if "butterfly_effects" in state_data:
        for effect in state_data["butterfly_effects"]:
            if isinstance(effect, dict):
                db.add_butterfly_effect(
                    description=effect.get("description", str(effect)),
                    chapter=effect.get("chapter"),
                    impact=effect.get("impact"),
                )
            else:
                db.add_butterfly_effect(description=str(effect))

    # Migrate context
    if "context" in state_data:
        ctx = state_data["context"]
        if "last_chapter_summary" in ctx:
            db.update_progress(last_chapter_summary=ctx["last_chapter_summary"])
        if "active_conflicts" in ctx:
            for conflict in ctx["active_conflicts"]:
                db.add_conflict(str(conflict))


def _migrate_memory(db: NovelDatabase, memory_data: dict[str, Any]) -> None:
    """Migrate memory.json data to database.

    Args:
        db: NovelDatabase instance
        memory_data: Parsed memory.json data
    """
    for category, items in memory_data.items():
        if isinstance(items, dict):
            for key, value in items.items():
                if isinstance(value, dict):
                    # Old format: {content: str, updated_at: str, ...}
                    content = value.get("content", str(value))
                else:
                    content = str(value)
                db.remember(category, key, content)


def _migrate_checkpoints(db: NovelDatabase, checkpoints_dir: Path) -> int:
    """Migrate checkpoint files to database.

    Args:
        db: NovelDatabase instance
        checkpoints_dir: Path to checkpoints directory

    Returns:
        Number of checkpoints migrated
    """
    migrated = 0
    for checkpoint_file in sorted(checkpoints_dir.glob("*.yaml")):
        try:
            checkpoint_data = yaml.safe_load(checkpoint_file.read_text(encoding="utf-8"))
            if checkpoint_data:
                # Extract name from filename (e.g., "20240101-120000-chapter-5.yaml")
                name = checkpoint_file.stem

                # Create a synthetic snapshot from the old checkpoint data
                snapshot = {
                    "progress": checkpoint_data.get("progress", {}),
                    "characters": checkpoint_data.get("characters", {}),
                    "foreshadowing": checkpoint_data.get("foreshadowing", []),
                    "memory": {},  # Old checkpoints didn't include memory
                }

                # Insert directly into checkpoints table
                with db._connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO checkpoints (name, checkpoint_type, snapshot)
                        VALUES (?, 'migrated', ?)
                    """,
                        (name, json.dumps(snapshot, ensure_ascii=False)),
                    )

                migrated += 1
        except Exception:
            # Skip invalid checkpoint files
            continue

    return migrated


def cleanup_old_files(project_path: Path, remove_backups: bool = False) -> list[str]:
    """Clean up old format files after successful migration.

    Args:
        project_path: Path to the novel project
        remove_backups: If True, also remove .bak files

    Returns:
        List of removed file paths
    """
    removed = []
    novel_dir = project_path / ".novel"

    # Only clean up if migration was successful (DB exists)
    if not (novel_dir / "novel.db").exists():
        return removed

    # Remove original files
    files_to_remove = [
        novel_dir / "state.yaml",
        novel_dir / "memory" / "memory.json",
    ]

    for file_path in files_to_remove:
        if file_path.exists():
            file_path.unlink()
            removed.append(str(file_path))

    # Remove empty memory directory
    memory_dir = novel_dir / "memory"
    if memory_dir.exists() and not any(memory_dir.iterdir()):
        memory_dir.rmdir()
        removed.append(str(memory_dir))

    # Optionally remove backup files
    if remove_backups:
        backup_files = [
            novel_dir / "state.yaml.bak",
            novel_dir / "memory" / "memory.json.bak",
        ]
        for backup_path in backup_files:
            if backup_path.exists():
                backup_path.unlink()
                removed.append(str(backup_path))

        backup_dir = novel_dir / "checkpoints.bak"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
            removed.append(str(backup_dir))

    return removed


def rollback_migration(project_path: Path) -> dict[str, Any]:
    """Rollback migration by restoring backup files.

    Args:
        project_path: Path to the novel project

    Returns:
        Rollback result dict
    """
    result: dict[str, Any] = {
        "success": False,
        "restored_files": [],
        "errors": [],
    }

    novel_dir = project_path / ".novel"
    db_file = novel_dir / "novel.db"

    try:
        # Restore state.yaml
        state_backup = novel_dir / "state.yaml.bak"
        state_file = novel_dir / "state.yaml"
        if state_backup.exists():
            shutil.copy2(state_backup, state_file)
            result["restored_files"].append("state.yaml")

        # Restore memory.json
        memory_backup = novel_dir / "memory" / "memory.json.bak"
        memory_file = novel_dir / "memory" / "memory.json"
        if memory_backup.exists():
            memory_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(memory_backup, memory_file)
            result["restored_files"].append("memory.json")

        # Restore checkpoints
        checkpoints_backup = novel_dir / "checkpoints.bak"
        checkpoints_dir = novel_dir / "checkpoints"
        if checkpoints_backup.exists():
            if checkpoints_dir.exists():
                shutil.rmtree(checkpoints_dir)
            shutil.copytree(checkpoints_backup, checkpoints_dir)
            result["restored_files"].append("checkpoints/")

        # Remove database and WAL files
        for db_file_path in [
            db_file,
            db_file.with_suffix(".db-wal"),
            db_file.with_suffix(".db-shm"),
        ]:
            if db_file_path.exists():
                db_file_path.unlink()

        result["success"] = True

    except Exception as e:
        result["errors"].append(f"Rollback failed: {e}")

    return result


def get_migration_status(project_path: Path) -> dict[str, Any]:
    """Get migration status for a project.

    Args:
        project_path: Path to the novel project

    Returns:
        Status dict with:
        - format: "sqlite" | "yaml" | "mixed" | "empty"
        - has_database: bool
        - has_yaml_state: bool
        - has_json_memory: bool
        - has_backups: bool
        - needs_migration: bool
    """
    novel_dir = project_path / ".novel"

    status = {
        "format": "empty",
        "has_database": False,
        "has_yaml_state": False,
        "has_json_memory": False,
        "has_backups": False,
        "needs_migration": False,
    }

    status["has_database"] = (novel_dir / "novel.db").exists()
    status["has_yaml_state"] = (novel_dir / "state.yaml").exists()
    status["has_json_memory"] = (novel_dir / "memory" / "memory.json").exists()
    status["has_backups"] = (novel_dir / "state.yaml.bak").exists() or (
        novel_dir / "memory" / "memory.json.bak"
    ).exists()

    if status["has_database"]:
        if status["has_yaml_state"] or status["has_json_memory"]:
            status["format"] = "mixed"
        else:
            status["format"] = "sqlite"
    elif status["has_yaml_state"] or status["has_json_memory"]:
        status["format"] = "yaml"
        status["needs_migration"] = True

    return status


__all__ = [
    "needs_migration",
    "migrate_project",
    "cleanup_old_files",
    "rollback_migration",
    "get_migration_status",
]
