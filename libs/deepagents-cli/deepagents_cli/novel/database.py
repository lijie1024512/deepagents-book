"""SQLite database management for novel projects.

This module provides ACID-compliant storage for novel project state,
replacing YAML/JSON files with a single SQLite database for reliability.

Key features:
- Atomic transactions for state consistency
- WAL mode for concurrent read/write safety
- Crash recovery via SQLite's journal
- Single source of truth (no state.yaml/memory.json sync issues)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# SQL schema for novel database
SCHEMA_SQL = """
-- Project configuration (read-only after creation)
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Progress state (single row)
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    outline_total INTEGER DEFAULT 50,
    outline_completed INTEGER DEFAULT 0,
    writing_total INTEGER DEFAULT 50,
    writing_completed INTEGER DEFAULT 0,
    current_chapter INTEGER DEFAULT 1,
    last_chapter_summary TEXT DEFAULT '',
    current_phase TEXT DEFAULT 'brainstorm',
    phase_completed TEXT DEFAULT '{}',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Character states
CREATE TABLE IF NOT EXISTS characters (
    name TEXT PRIMARY KEY,
    location TEXT DEFAULT '未知',
    status TEXT DEFAULT '未出场',
    power_level TEXT DEFAULT '未知',
    relationships TEXT DEFAULT '{}',
    last_appearance INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Foreshadowing management
CREATE TABLE IF NOT EXISTS foreshadowing (
    name TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    planted_chapter INTEGER,
    target_chapter INTEGER,
    resolved INTEGER DEFAULT 0,
    resolved_chapter INTEGER,
    resolution TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Memory storage (replaces memory.json)
CREATE TABLE IF NOT EXISTS memory (
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (category, key)
);

-- Checkpoints for state snapshots
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    checkpoint_type TEXT DEFAULT 'auto',
    snapshot TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Operation log for crash recovery
CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    details TEXT,
    status TEXT DEFAULT 'started',
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Active conflicts tracking
CREATE TABLE IF NOT EXISTS active_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Butterfly effects tracking
CREATE TABLE IF NOT EXISTS butterfly_effects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    chapter INTEGER,
    impact TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class NovelDatabase:
    """SQLite-based storage for novel project data.

    Provides ACID-compliant operations for all project state,
    replacing multiple YAML/JSON files with a single database.
    """

    def __init__(self, project_path: Path):
        """Initialize database for a project.

        Args:
            project_path: Path to the novel project directory
        """
        self.project_path = project_path
        self.db_path = project_path / ".novel" / "novel.db"
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(SCHEMA_SQL)
            # Ensure progress table has initial row
            conn.execute("INSERT OR IGNORE INTO progress (id) VALUES (1)")
            # Migrate: add phase columns for existing databases
            self._migrate_phase_columns(conn)

    def _migrate_phase_columns(self, conn: sqlite3.Connection) -> None:
        """Add current_phase and phase_completed columns if missing (for existing DBs)."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(progress)").fetchall()}
        if "current_phase" not in columns:
            conn.execute("ALTER TABLE progress ADD COLUMN current_phase TEXT DEFAULT 'brainstorm'")
        if "phase_completed" not in columns:
            conn.execute("ALTER TABLE progress ADD COLUMN phase_completed TEXT DEFAULT '{}'")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Get database connection with WAL mode enabled.

        Yields:
            SQLite connection with row_factory set for dict-like access
        """
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")  # Concurrent safety
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Transaction context for atomic multi-statement operations.

        Yields:
            SQLite connection within a transaction

        Example:
            with db.transaction() as conn:
                conn.execute("UPDATE ...")
                conn.execute("INSERT ...")
            # Auto-commits on success, rollbacks on exception
        """
        with self._connection() as conn:
            conn.execute("BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # =========================================================================
    # Progress Operations
    # =========================================================================

    def get_progress(self) -> dict[str, Any]:
        """Get current progress state.

        Returns:
            Dict with progress fields (phase_completed deserialized from JSON)
        """
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM progress WHERE id=1").fetchone()
            if not row:
                return {}
            result = dict(row)
            # Deserialize phase_completed from JSON string to dict
            pc = result.get("phase_completed", "{}")
            if isinstance(pc, str):
                result["phase_completed"] = json.loads(pc) if pc else {}
            return result

    def update_progress(self, **kwargs: Any) -> None:
        """Update progress fields.

        Args:
            **kwargs: Fields to update (outline_total, outline_completed,
                      writing_total, writing_completed, current_chapter,
                      last_chapter_summary)
        """
        valid_keys = {
            "outline_total",
            "outline_completed",
            "writing_total",
            "writing_completed",
            "current_chapter",
            "last_chapter_summary",
            "current_phase",
            "phase_completed",
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_keys}
        if not updates:
            return
        # Serialize phase_completed dict to JSON string
        if "phase_completed" in updates and isinstance(updates["phase_completed"], dict):
            updates["phase_completed"] = json.dumps(updates["phase_completed"], ensure_ascii=False)
        set_clause = ", ".join(f"{k}=?" for k in updates)
        with self._connection() as conn:
            conn.execute(
                f"UPDATE progress SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                list(updates.values()),
            )

    # =========================================================================
    # Character Operations
    # =========================================================================

    def get_character(self, name: str) -> dict[str, Any] | None:
        """Get character by name.

        Args:
            name: Character name

        Returns:
            Character dict or None if not found
        """
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM characters WHERE name=?", (name,)).fetchone()
            if row:
                d = dict(row)
                d["relationships"] = json.loads(d["relationships"] or "{}")
                return d
            return None

    def update_character(self, name: str, **kwargs: Any) -> None:
        """Update or create character.

        Args:
            name: Character name
            **kwargs: Fields to update (location, status, power_level,
                      relationships, last_appearance, notes)
        """
        existing = self.get_character(name)

        # Convert relationships to JSON if provided
        if "relationships" in kwargs:
            kwargs["relationships"] = json.dumps(kwargs["relationships"], ensure_ascii=False)

        if existing:
            # Update existing character
            if not kwargs:
                return
            set_clause = ", ".join(f"{k}=?" for k in kwargs)
            with self._connection() as conn:
                conn.execute(
                    f"UPDATE characters SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE name=?",
                    [*kwargs.values(), name],
                )
        else:
            # Insert new character
            kwargs["name"] = name
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" * len(kwargs))
            with self._connection() as conn:
                conn.execute(
                    f"INSERT INTO characters ({cols}) VALUES ({placeholders})",
                    list(kwargs.values()),
                )

    def delete_character(self, name: str) -> bool:
        """Delete a character.

        Args:
            name: Character name

        Returns:
            True if deleted, False if not found
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM characters WHERE name=?", (name,))
            return cursor.rowcount > 0

    def list_characters(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        """List all characters, optionally filtered by status.

        Args:
            status_filter: Optional status to filter by

        Returns:
            List of character dicts
        """
        with self._connection() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM characters WHERE status=? ORDER BY name", (status_filter,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM characters ORDER BY name").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["relationships"] = json.loads(d["relationships"] or "{}")
                result.append(d)
            return result

    def add_relationship(
        self, character: str, target: str, relation: str, mutual: bool = False
    ) -> None:
        """Add a relationship between characters.

        Args:
            character: Source character name
            target: Target character name
            relation: Relationship description
            mutual: If True, add reverse relationship too
        """
        # Get or create source character
        char_data = self.get_character(character)
        if char_data is None:
            char_data = {"relationships": {}}

        relationships = char_data.get("relationships", {})
        relationships[target] = relation
        self.update_character(character, relationships=relationships)

        if mutual:
            # Add reverse relationship
            target_data = self.get_character(target)
            if target_data is None:
                target_data = {"relationships": {}}
            target_rels = target_data.get("relationships", {})
            target_rels[character] = relation
            self.update_character(target, relationships=target_rels)

    # =========================================================================
    # Foreshadowing Operations
    # =========================================================================

    def plant_foreshadow(
        self, name: str, content: str, chapter: int | None = None, target_chapter: int | None = None
    ) -> None:
        """Plant a foreshadow.

        Args:
            name: Foreshadow identifier
            content: Foreshadow content/description
            chapter: Chapter where planted
            target_chapter: Target chapter for resolution
        """
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO foreshadowing
                (name, content, planted_chapter, target_chapter, resolved, created_at)
                VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            """,
                (name, content, chapter, target_chapter),
            )

    def resolve_foreshadow(
        self, name: str, resolved_chapter: int, resolution: str | None = None
    ) -> bool:
        """Mark a foreshadow as resolved.

        Args:
            name: Foreshadow identifier
            resolved_chapter: Chapter where resolved
            resolution: Optional description of resolution

        Returns:
            True if updated, False if not found
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE foreshadowing
                SET resolved=1, resolved_chapter=?, resolution=?
                WHERE name=?
            """,
                (resolved_chapter, resolution, name),
            )
            return cursor.rowcount > 0

    def get_foreshadow(self, name: str) -> dict[str, Any] | None:
        """Get foreshadow by name.

        Args:
            name: Foreshadow identifier

        Returns:
            Foreshadow dict or None
        """
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM foreshadowing WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None

    def list_foreshadows(self, include_resolved: bool = False) -> list[dict[str, Any]]:
        """List foreshadows.

        Args:
            include_resolved: Whether to include resolved foreshadows

        Returns:
            List of foreshadow dicts
        """
        with self._connection() as conn:
            if include_resolved:
                rows = conn.execute(
                    "SELECT * FROM foreshadowing ORDER BY planted_chapter"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM foreshadowing WHERE resolved=0 ORDER BY planted_chapter"
                ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Memory Operations (replaces memory.json)
    # =========================================================================

    def remember(self, category: str, key: str, content: str) -> None:
        """Store memory entry.

        Args:
            category: Memory category (character, plot, foreshadow, setting, decision, summary)
            key: Memory key/identifier
            content: Memory content
        """
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory (category, key, content, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (category, key, content),
            )

    def recall(self, category: str | None = None, key: str | None = None) -> dict[str, Any]:
        """Retrieve memory entries.

        Args:
            category: Optional category filter
            key: Optional key filter (requires category)

        Returns:
            - If both category and key: {"content": str} or {}
            - If only category: {key: content, ...}
            - If neither: {category: {key: content, ...}, ...}
        """
        with self._connection() as conn:
            if category and key:
                row = conn.execute(
                    "SELECT content FROM memory WHERE category=? AND key=?", (category, key)
                ).fetchone()
                return {"content": row["content"]} if row else {}
            elif category:
                rows = conn.execute(
                    "SELECT key, content FROM memory WHERE category=?", (category,)
                ).fetchall()
                return {r["key"]: r["content"] for r in rows}
            else:
                rows = conn.execute("SELECT category, key, content FROM memory").fetchall()
                result: dict[str, dict[str, str]] = {}
                for r in rows:
                    result.setdefault(r["category"], {})[r["key"]] = r["content"]
                return result

    def forget(self, category: str, key: str) -> bool:
        """Delete a memory entry.

        Args:
            category: Memory category
            key: Memory key

        Returns:
            True if deleted, False if not found
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM memory WHERE category=? AND key=?", (category, key))
            return cursor.rowcount > 0

    def update_memory(self, category: str, key: str, content: str) -> None:
        """Append content to existing memory or create new.

        Args:
            category: Memory category
            key: Memory key
            content: Content to append
        """
        existing = self.recall(category, key)
        if existing and "content" in existing:
            new_content = f"{existing['content']}\n\n---\n{content}"
            self.remember(category, key, new_content)
        else:
            self.remember(category, key, content)

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    def create_checkpoint(self, name: str | None = None) -> int:
        """Create a state checkpoint.

        Args:
            name: Optional checkpoint name (for manual checkpoints)

        Returns:
            Checkpoint ID
        """
        snapshot = {
            "progress": self.get_progress(),
            "characters": self.list_characters(),
            "foreshadowing": self.list_foreshadows(include_resolved=True),
            "memory": self.recall(),
            "active_conflicts": self.list_active_conflicts(),
            "butterfly_effects": self.list_butterfly_effects(),
        }
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO checkpoints (name, checkpoint_type, snapshot)
                VALUES (?, ?, ?)
            """,
                (name, "manual" if name else "auto", json.dumps(snapshot, ensure_ascii=False)),
            )

            # Clean up old checkpoints (keep last 20)
            conn.execute("""
                DELETE FROM checkpoints WHERE id NOT IN (
                    SELECT id FROM checkpoints ORDER BY id DESC LIMIT 20
                )
            """)
            return cursor.lastrowid or 0

    def restore_checkpoint(self, checkpoint_id: int) -> bool:
        """Restore state from a checkpoint.

        Args:
            checkpoint_id: ID of checkpoint to restore

        Returns:
            True if restored, False if checkpoint not found
        """
        with self._connection() as conn:
            row = conn.execute(
                "SELECT snapshot FROM checkpoints WHERE id=?", (checkpoint_id,)
            ).fetchone()
            if not row:
                return False

            snapshot = json.loads(row["snapshot"])

            # Use transaction for atomic restore
            conn.execute("BEGIN")
            try:
                # Restore progress
                p = snapshot.get("progress", {})
                if p:
                    phase_completed = p.get("phase_completed", {})
                    if isinstance(phase_completed, dict):
                        phase_completed = json.dumps(phase_completed, ensure_ascii=False)
                    conn.execute(
                        """
                        UPDATE progress SET
                        outline_total=?, outline_completed=?,
                        writing_total=?, writing_completed=?,
                        current_chapter=?, last_chapter_summary=?,
                        current_phase=?, phase_completed=?,
                        updated_at=CURRENT_TIMESTAMP
                        WHERE id=1
                    """,
                        (
                            p.get("outline_total", 0),
                            p.get("outline_completed", 0),
                            p.get("writing_total", 0),
                            p.get("writing_completed", 0),
                            p.get("current_chapter", 1),
                            p.get("last_chapter_summary", ""),
                            p.get("current_phase", "brainstorm"),
                            phase_completed if isinstance(phase_completed, str) else "{}",
                        ),
                    )

                # Restore characters
                conn.execute("DELETE FROM characters")
                for c in snapshot.get("characters", []):
                    rels = c.get("relationships", {})
                    if isinstance(rels, dict):
                        rels = json.dumps(rels, ensure_ascii=False)
                    conn.execute(
                        """
                        INSERT INTO characters (name, location, status, power_level,
                                               relationships, last_appearance, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            c["name"],
                            c.get("location", "未知"),
                            c.get("status", "未出场"),
                            c.get("power_level", "未知"),
                            rels,
                            c.get("last_appearance", 0),
                            c.get("notes", ""),
                        ),
                    )

                # Restore foreshadowing
                conn.execute("DELETE FROM foreshadowing")
                for f in snapshot.get("foreshadowing", []):
                    conn.execute(
                        """
                        INSERT INTO foreshadowing (name, content, planted_chapter,
                                                  target_chapter, resolved, resolved_chapter, resolution)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            f["name"],
                            f["content"],
                            f.get("planted_chapter"),
                            f.get("target_chapter"),
                            f.get("resolved", 0),
                            f.get("resolved_chapter"),
                            f.get("resolution"),
                        ),
                    )

                # Restore memory
                conn.execute("DELETE FROM memory")
                for cat, items in snapshot.get("memory", {}).items():
                    for key, content in items.items():
                        conn.execute(
                            "INSERT INTO memory (category, key, content) VALUES (?, ?, ?)",
                            (cat, key, content),
                        )

                # Restore active conflicts
                conn.execute("DELETE FROM active_conflicts")
                for conflict in snapshot.get("active_conflicts", []):
                    if isinstance(conflict, dict):
                        conn.execute(
                            "INSERT INTO active_conflicts (description) VALUES (?)",
                            (conflict.get("description", ""),),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO active_conflicts (description) VALUES (?)", (conflict,)
                        )

                # Restore butterfly effects
                conn.execute("DELETE FROM butterfly_effects")
                for effect in snapshot.get("butterfly_effects", []):
                    if isinstance(effect, dict):
                        conn.execute(
                            """
                            INSERT INTO butterfly_effects (description, chapter, impact)
                            VALUES (?, ?, ?)
                        """,
                            (
                                effect.get("description", ""),
                                effect.get("chapter"),
                                effect.get("impact"),
                            ),
                        )

                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """List all checkpoints.

        Returns:
            List of checkpoint metadata (id, name, type, created_at)
        """
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT id, name, checkpoint_type, created_at
                FROM checkpoints ORDER BY id DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Operation Log (for crash recovery)
    # =========================================================================

    def log_operation_start(self, operation: str, details: dict[str, Any]) -> int:
        """Log start of an operation.

        Args:
            operation: Operation name
            details: Operation details

        Returns:
            Log entry ID
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO operation_log (operation, details, status)
                VALUES (?, ?, 'started')
            """,
                (operation, json.dumps(details, ensure_ascii=False)),
            )
            return cursor.lastrowid or 0

    def log_operation_complete(self, log_id: int) -> None:
        """Mark operation as completed.

        Args:
            log_id: Log entry ID
        """
        with self._connection() as conn:
            conn.execute("UPDATE operation_log SET status='completed' WHERE id=?", (log_id,))

    def log_operation_failed(self, log_id: int, error: str) -> None:
        """Mark operation as failed.

        Args:
            log_id: Log entry ID
            error: Error message
        """
        with self._connection() as conn:
            conn.execute(
                "UPDATE operation_log SET status='failed', error=? WHERE id=?", (error, log_id)
            )

    def get_pending_operations(self) -> list[dict[str, Any]]:
        """Get operations that were started but not completed.

        Returns:
            List of pending operation dicts
        """
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM operation_log WHERE status='started'").fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Active Conflicts
    # =========================================================================

    def add_conflict(self, description: str) -> int:
        """Add an active conflict.

        Args:
            description: Conflict description

        Returns:
            Conflict ID
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO active_conflicts (description) VALUES (?)", (description,)
            )
            return cursor.lastrowid or 0

    def remove_conflict(self, conflict_id: int) -> bool:
        """Remove an active conflict.

        Args:
            conflict_id: Conflict ID

        Returns:
            True if removed, False if not found
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM active_conflicts WHERE id=?", (conflict_id,))
            return cursor.rowcount > 0

    def list_active_conflicts(self) -> list[dict[str, Any]]:
        """List all active conflicts.

        Returns:
            List of conflict dicts
        """
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM active_conflicts ORDER BY created_at").fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Butterfly Effects
    # =========================================================================

    def add_butterfly_effect(
        self, description: str, chapter: int | None = None, impact: str | None = None
    ) -> int:
        """Add a butterfly effect.

        Args:
            description: Effect description
            chapter: Related chapter
            impact: Impact description

        Returns:
            Effect ID
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO butterfly_effects (description, chapter, impact)
                VALUES (?, ?, ?)
            """,
                (description, chapter, impact),
            )
            return cursor.lastrowid or 0

    def list_butterfly_effects(self) -> list[dict[str, Any]]:
        """List all butterfly effects.

        Returns:
            List of effect dicts
        """
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM butterfly_effects ORDER BY chapter, created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Config Operations
    # =========================================================================

    def get_config(self, key: str) -> str | None:
        """Get config value.

        Args:
            key: Config key

        Returns:
            Config value or None
        """
        with self._connection() as conn:
            row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

    def set_config(self, key: str, value: str) -> None:
        """Set config value.

        Args:
            key: Config key
            value: Config value
        """
        with self._connection() as conn:
            conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))

    def get_all_config(self) -> dict[str, str]:
        """Get all config values.

        Returns:
            Dict of all config key-value pairs
        """
        with self._connection() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            return {r["key"]: r["value"] for r in rows}


__all__ = ["NovelDatabase", "SCHEMA_SQL"]
