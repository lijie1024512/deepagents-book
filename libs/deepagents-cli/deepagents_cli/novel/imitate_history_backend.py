"""Read-only backend mapping virtual /history/ paths to SQLite queries.

Provides a structured view of the novel imitation project's
progressive history through the standard BackendProtocol interface.
The CompositeBackend routes ``/history/`` to this backend so that
``read_file("/history/overview.md")`` works transparently.

Virtual file structure::

    /overview.md        All chapters with summaries + stats
    /chapter-{N}.md     Chapter N full record (content + evolution)
    /characters.md      All character evolution trajectories
    /golden-finger.md   Full golden finger evolution history
    /creative-log.md    All creative deviation records
"""

from __future__ import annotations

import logging
import re

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.utils import format_content_with_line_numbers

from deepagents_cli.novel.imitate_tools import _get_db

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(r"^/chapter-(\d+)\.md$")

_KNOWN_FILES = (
    "/overview.md",
    "/characters.md",
    "/golden-finger.md",
    "/creative-log.md",
    "/skills.md",
)

_READ_ONLY_MSG = "History backend is read-only."


class ImitateHistoryBackend(BackendProtocol):
    """Read-only backend exposing imitation project history.

    Only ``read()`` and ``ls_info()`` return meaningful data.
    All write operations return appropriate errors.
    """

    # ------------------------------------------------------------------
    # Core read operations
    # ------------------------------------------------------------------

    def ls_info(self, path: str) -> list[FileInfo]:
        """List available virtual history files.

        Args:
            path: Directory path (only ``/`` is meaningful).

        Returns:
            List of FileInfo for files that have data in DB.
        """
        if path not in ("/", ""):
            return []

        db = _get_db()
        if db is None:
            return []

        results: list[FileInfo] = []

        with db._connection() as conn:
            # Always list overview
            results.append({"path": "/overview.md", "is_dir": False})

            # List each chapter
            chapters = conn.execute(
                "SELECT chapter FROM imitate_chapters ORDER BY chapter"
            ).fetchall()
            for (ch,) in chapters:
                results.append(
                    {
                        "path": f"/chapter-{ch}.md",
                        "is_dir": False,
                    }
                )

            # Conditional files
            if conn.execute("SELECT 1 FROM imitate_character_evolution LIMIT 1").fetchone():
                results.append(
                    {
                        "path": "/characters.md",
                        "is_dir": False,
                    }
                )

            if conn.execute("SELECT 1 FROM imitate_power_evolution LIMIT 1").fetchone():
                results.append(
                    {
                        "path": "/golden-finger.md",
                        "is_dir": False,
                    }
                )

            if conn.execute("SELECT 1 FROM imitate_creative_log LIMIT 1").fetchone():
                results.append(
                    {
                        "path": "/creative-log.md",
                        "is_dir": False,
                    }
                )

            try:
                if conn.execute("SELECT 1 FROM imitate_skill_library LIMIT 1").fetchone():
                    results.append(
                        {
                            "path": "/skills.md",
                            "is_dir": False,
                        }
                    )
            except Exception:  # noqa: BLE001, S110
                pass  # Table may not exist in older databases

        return results

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read a virtual history file.

        Routes to the appropriate ``_render_*`` method based on
        path, then formats output with line numbers.

        Args:
            file_path: Virtual file path (e.g. ``/overview.md``).
            offset: Line offset (0-indexed).
            limit: Max lines to return.

        Returns:
            Formatted content with line numbers (cat -n style).
        """
        content = self._render_file(file_path)

        # Apply offset/limit via format helper
        lines = content.split("\n")
        sliced = lines[offset : offset + limit]
        return format_content_with_line_numbers("\n".join(sliced), start_line=offset + 1)

    # ------------------------------------------------------------------
    # Render methods — one per virtual file
    # ------------------------------------------------------------------

    def _render_file(self, file_path: str) -> str:
        """Dispatch to the correct renderer.

        Args:
            file_path: Virtual path like ``/overview.md``.

        Returns:
            Raw markdown string.
        """
        if file_path == "/overview.md":
            return self._render_overview()

        m = _CHAPTER_RE.match(file_path)
        if m:
            return self._render_chapter(int(m.group(1)))

        dispatch = {
            "/characters.md": self._render_characters,
            "/golden-finger.md": self._render_golden_finger,
            "/creative-log.md": self._render_creative_log,
            "/skills.md": self._render_skills,
        }
        renderer = dispatch.get(file_path)
        if renderer:
            return renderer()

        return f"Error: File '{file_path}' not found."

    def _render_overview(self) -> str:
        """Render ``/overview.md``: chapter list with summaries."""
        db = _get_db()
        if db is None:
            return "Error: Database not available."

        with db._connection() as conn:
            chapters = conn.execute(
                "SELECT chapter, title, LENGTH(content), "
                "summary FROM imitate_chapters "
                "ORDER BY chapter"
            ).fetchall()

        if not chapters:
            return "# 仿写项目进度\n\n尚未生成任何章节。"

        total_chars = sum(r[2] or 0 for r in chapters)
        lines = [
            "# 仿写项目进度",
            "",
            f"已生成: {len(chapters)} 章 | 总字数: 约 {total_chars:,} 字",
            "",
            "## 章节概览",
            "",
        ]

        for ch, title, char_count, summary in chapters:
            t = title or ""
            c = f"{char_count or 0:,}"
            s = (summary or "（无摘要）")[:120]
            if summary and len(summary) > 120:
                s += "..."
            heading = f"### 第{ch}章"
            if t:
                heading += f" 《{t}》"
            heading += f"（{c}字）"
            lines.append(heading)
            lines.append(f"{s}")
            lines.append("")

        return "\n".join(lines)

    def _render_chapter(self, chapter: int) -> str:
        """Render ``/chapter-{N}.md``: full chapter record."""
        db = _get_db()
        if db is None:
            return "Error: Database not available."

        with db._connection() as conn:
            row = conn.execute(
                "SELECT chapter, title, content, summary FROM imitate_chapters WHERE chapter=?",
                (chapter,),
            ).fetchone()

        if not row:
            return f"Error: File '/chapter-{chapter}.md' not found."

        _, title, content, summary = row
        heading = f"# 第{chapter}章"
        if title:
            heading += f" 《{title}》"

        lines = [heading, ""]

        # Summary first (most useful for quick review)
        if summary:
            lines.extend(["## 摘要", summary, ""])

        # Full content
        char_count = len(content) if content else 0
        lines.extend([f"## 正文（{char_count:,}字）", "", content or "", ""])

        # Character evolution for this chapter
        with db._connection() as conn:
            char_evos = conn.execute(
                "SELECT character_name, changes, "
                "personality_shift, relationship_changes "
                "FROM imitate_character_evolution "
                "WHERE chapter=?",
                (chapter,),
            ).fetchall()

        if char_evos:
            lines.extend(["## 角色演化", ""])
            for name, changes, personality, rels in char_evos:
                parts = [f"- **{name}**: {changes}"]
                if personality:
                    parts.append(f"  性格偏移: {personality}")
                if rels:
                    parts.append(f"  关系变化: {rels}")
                lines.extend(parts)
            lines.append("")

        # Golden finger evolution for this chapter
        with db._connection() as conn:
            power = conn.execute(
                "SELECT ability_unlocked, "
                "limitation_discovered, usage_context, "
                "evolution_note "
                "FROM imitate_power_evolution "
                "WHERE chapter=?",
                (chapter,),
            ).fetchone()

        if power:
            ability, limitation, context, note = power
            lines.extend(["## 金手指演化", ""])
            if ability:
                lines.append(f"- 能力: {ability}")
            if limitation:
                lines.append(f"- 限制: {limitation}")
            if context:
                lines.append(f"- 情境: {context}")
            if note:
                lines.append(f"- 变化: {note}")
            lines.append("")

        # Creative log for this chapter
        with db._connection() as conn:
            creative = conn.execute(
                "SELECT category, source_original, "
                "adapted_version, reason "
                "FROM imitate_creative_log "
                "WHERE chapter=?",
                (chapter,),
            ).fetchall()

        if creative:
            cat_cn = {
                "plot": "情节",
                "character": "角色",
                "golden_finger": "金手指",
                "setting": "设定",
            }
            lines.extend(["## 创意偏离", ""])
            for cat, src, adapted, reason in creative:
                label = cat_cn.get(cat, cat)
                entry = f"- [{label}] 源: {src} → 改: {adapted}"
                if reason:
                    entry += f"（{reason}）"
                lines.append(entry)
            lines.append("")

        return "\n".join(lines)

    def _render_characters(self) -> str:
        """Render ``/characters.md``: all character trajectories."""
        db = _get_db()
        if db is None:
            return "Error: Database not available."

        with db._connection() as conn:
            rows = conn.execute(
                "SELECT character_name, chapter, changes, "
                "personality_shift, relationship_changes "
                "FROM imitate_character_evolution "
                "ORDER BY character_name, chapter"
            ).fetchall()

        if not rows:
            return "# 角色演化轨迹\n\n尚无记录。"

        lines = ["# 角色演化轨迹", ""]
        current_char = ""
        for name, ch, changes, personality, rels in rows:
            if name != current_char:
                current_char = name
                lines.extend(["", f"## {name}", ""])
            entry = f"- 第{ch}章: {changes}"
            if personality:
                entry += f" | 性格: {personality}"
            if rels:
                entry += f" | 关系: {rels}"
            lines.append(entry)

        return "\n".join(lines)

    def _render_golden_finger(self) -> str:
        """Render ``/golden-finger.md``: full evolution history."""
        db = _get_db()
        if db is None:
            return "Error: Database not available."

        lines = ["# 金手指演化历程", ""]

        # Base design from analysis
        with db._connection() as conn:
            base = conn.execute(
                "SELECT content FROM imitate_analysis WHERE key='power_system'"
            ).fetchone()

        if base and base[0]:
            text = base[0]
            if len(text) > 2000:
                text = (
                    text[:2000]
                    + "\n...(基础设计已截取，"
                    + '完整版用 get_analysis("power_system"))'
                )
            lines.extend(["## 基础设计", "", text, ""])

        # Evolution timeline
        with db._connection() as conn:
            evos = conn.execute(
                "SELECT chapter, ability_unlocked, "
                "limitation_discovered, usage_context, "
                "evolution_note "
                "FROM imitate_power_evolution "
                "ORDER BY chapter"
            ).fetchall()

        if evos:
            lines.extend(["## 演化时间线", ""])
            for ch, ability, limit_, ctx, note in evos:
                parts = [f"### 第{ch}章"]
                if ability:
                    parts.append(f"- 解锁能力: {ability}")
                if limit_:
                    parts.append(f"- 发现限制: {limit_}")
                if ctx:
                    parts.append(f"- 使用情境: {ctx}")
                if note:
                    parts.append(f"- 演化备注: {note}")
                parts.append("")
                lines.extend(parts)

            # Current state
            latest_ch = evos[-1][0]
            lines.append(f"**当前状态**（第{latest_ch}章后）：已记录 {len(evos)} 次演化")
        elif not base:
            lines.append("尚无金手指设计或演化记录。")

        return "\n".join(lines)

    def _render_creative_log(self) -> str:
        """Render ``/creative-log.md``: all creative deviations."""
        db = _get_db()
        if db is None:
            return "Error: Database not available."

        with db._connection() as conn:
            rows = conn.execute(
                "SELECT chapter, category, source_original, "
                "adapted_version, reason "
                "FROM imitate_creative_log "
                "ORDER BY chapter, id"
            ).fetchall()

        if not rows:
            return "# 创意偏离记录\n\n尚无记录。"

        cat_cn = {
            "plot": "情节",
            "character": "角色",
            "golden_finger": "金手指",
            "setting": "设定",
        }

        lines = ["# 创意偏离记录", ""]
        current_ch = -1
        for ch, cat, src, adapted, reason in rows:
            if ch != current_ch:
                current_ch = ch
                lines.extend(["", f"## 第{ch}章", ""])
            label = cat_cn.get(cat, cat)
            entry = f"- [{label}] 源: {src} → 改: {adapted}"
            if reason:
                entry += f"（{reason}）"
            lines.append(entry)

        # Distribution summary
        with db._connection() as conn:
            dist = conn.execute(
                "SELECT category, COUNT(*) "
                "FROM imitate_creative_log "
                "GROUP BY category ORDER BY COUNT(*) DESC"
            ).fetchall()

        if dist:
            total = sum(c for _, c in dist)
            dist_parts = []
            for cat, count in dist:
                label = cat_cn.get(cat, cat)
                pct = round(count / total * 100)
                dist_parts.append(f"{label} {pct}%")
            lines.extend(
                [
                    "",
                    "---",
                    f"**偏离分布**: {'、'.join(dist_parts)}",
                ]
            )

        return "\n".join(lines)

    def _render_skills(self) -> str:
        """Render ``/skills.md``: user feedback skill library."""
        db = _get_db()
        if db is None:
            return "Error: Database not available."

        try:
            with db._connection() as conn:
                rows = conn.execute(
                    "SELECT chapter, skill_type, category, content "
                    "FROM imitate_skill_library "
                    "ORDER BY chapter, id"
                ).fetchall()
        except Exception:  # noqa: BLE001
            return "# 写作经验库\n\n尚无记录。"

        if not rows:
            return "# 写作经验库\n\n尚无记录。"

        type_cn = {
            "success_pattern": "成功模式",
            "lesson_learned": "经验教训",
        }

        lines = ["# 写作经验库", ""]
        current_ch = -1
        for ch, skill_type, category, content in rows:
            if ch != current_ch:
                current_ch = ch
                lines.extend(["", f"## 第{ch}章", ""])
            label = type_cn.get(skill_type, skill_type)
            lines.append(f"- [{label} / {category}] {content}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Read-only stubs
    # ------------------------------------------------------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        """Not supported (read-only)."""
        return WriteResult(error=_READ_ONLY_MSG)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Not supported (read-only)."""
        return EditResult(error=_READ_ONLY_MSG)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Not supported."""
        return []

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Return all files when pattern matches."""
        if "*" in pattern:
            return self.ls_info("/")
        return []

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Not supported (read-only)."""
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download virtual files as bytes."""
        results: list[FileDownloadResponse] = []
        for p in paths:
            content = self._render_file(p)
            if content.startswith("Error:"):
                results.append(
                    FileDownloadResponse(
                        path=p,
                        content=None,
                        error="file_not_found",
                    )
                )
            else:
                results.append(
                    FileDownloadResponse(
                        path=p,
                        content=content.encode("utf-8"),
                        error=None,
                    )
                )
        return results


__all__ = ["ImitateHistoryBackend"]
