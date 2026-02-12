"""Imitation (仿写) tools for novel writing.

Agent-driven novel imitation workflow:
- Index and read source novel chapters on demand
- Search source text for specific scenes/keywords
- Save/retrieve any analysis results flexibly (key-value store)
- Generate and save adapted chapters with source text as style reference
- No phase locks — the agent decides what to do and when

Uses the same NovelDatabase instance as the main novel module, with
additional imitate_* tables created on first use.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.tools import tool

from deepagents_cli.novel.chunker import (
    ChapterInfo,
    SourceIndex,
    index_source_novel,
    load_chapter_range_text,
    load_chapter_text,
    search_source_text,
)

if TYPE_CHECKING:
    from deepagents_cli.novel.database import NovelDatabase

# ---------------------------------------------------------------------------
# Module-level state (same pattern as memory_tools.py)
# ---------------------------------------------------------------------------
_imitate_project_path: Path | None = None
_imitate_db: NovelDatabase | None = None
_source_index: SourceIndex | None = None

# ---------------------------------------------------------------------------
# Schema — simplified: source metadata + key-value analysis + chapters
# ---------------------------------------------------------------------------
IMITATE_SCHEMA_SQL = """
-- Source novel metadata
CREATE TABLE IF NOT EXISTS imitate_source (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    file_path TEXT NOT NULL,
    file_size INTEGER,
    total_chars INTEGER,
    total_chapters INTEGER,
    encoding TEXT DEFAULT 'utf-8',
    chapter_index TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Flexible key-value store for all analysis results
CREATE TABLE IF NOT EXISTS imitate_analysis (
    key TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Generated chapters
CREATE TABLE IF NOT EXISTS imitate_chapters (
    chapter INTEGER PRIMARY KEY,
    title TEXT DEFAULT '',
    content TEXT,
    summary TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
def init_imitate_store(project_path: Path) -> None:
    """Initialize the imitate module state and database tables.

    Also auto-detects source file if the imitate_source table is empty
    but a source file exists in the project's source/ directory (handles
    the case where the database was deleted and recreated).

    Args:
        project_path: Path to the novel project directory.
    """
    global _imitate_project_path, _imitate_db, _source_index  # noqa: PLW0603

    # Only reset source index cache if the project path actually changed
    if _imitate_project_path != project_path:
        _source_index = None

    _imitate_project_path = project_path

    from deepagents_cli.novel.database import NovelDatabase

    _imitate_db = NovelDatabase(project_path)

    with _imitate_db._connection() as conn:
        conn.executescript(IMITATE_SCHEMA_SQL)

        # Auto-populate source if table is empty but source file exists on disk
        row = conn.execute("SELECT 1 FROM imitate_source WHERE id=1").fetchone()
        if row is None:
            source_dir = project_path / "source"
            if source_dir.exists():
                for f in sorted(source_dir.iterdir()):
                    if f.is_file() and f.suffix in (".txt", ".text"):
                        rel_path = f"source/{f.name}"
                        file_size = f.stat().st_size
                        conn.execute(
                            "INSERT INTO imitate_source (id, file_path, file_size) VALUES (1, ?, ?)",
                            (rel_path, file_size),
                        )
                        break


def _get_db() -> NovelDatabase | None:
    """Get the database instance."""
    return _imitate_db


def _get_source_path() -> Path | None:
    """Get the source novel file path from the database."""
    db = _get_db()
    if db is None:
        return None
    with db._connection() as conn:
        row = conn.execute("SELECT file_path FROM imitate_source WHERE id=1").fetchone()
    if row is None:
        return None
    rel_path = row[0]
    if _imitate_project_path is None:
        return None
    return _imitate_project_path / rel_path


def _restore_index_from_db(source_path: Path) -> SourceIndex | None:
    """Try to restore a SourceIndex from the database's chapter_index JSON.

    Returns None if the DB doesn't have valid data or the file has changed.
    """
    db = _get_db()
    if db is None:
        return None

    with db._connection() as conn:
        row = conn.execute(
            "SELECT file_size, total_chars, encoding, chapter_index FROM imitate_source WHERE id=1"
        ).fetchone()

    if not row or not row[3]:
        return None

    # Check if the source file size matches (detect if file changed)
    saved_file_size = row[0]
    current_file_size = source_path.stat().st_size
    if saved_file_size and saved_file_size != current_file_size:
        return None

    try:
        chapter_data = json.loads(row[3])
    except (json.JSONDecodeError, TypeError):
        return None

    if not chapter_data or not isinstance(chapter_data, list):
        return None

    # Check if chapter data has byte offsets (newer format)
    first = chapter_data[0]
    if "byte_offset" not in first:
        return None  # Old format without byte info, need full scan

    chapters = [
        ChapterInfo(
            chapter_id=ch["id"],
            title=ch.get("title", ""),
            char_offset=ch.get("char_offset", 0),
            byte_offset=ch["byte_offset"],
            char_count=ch.get("chars", 0),
            byte_count=ch.get("byte_count", 0),
        )
        for ch in chapter_data
    ]

    total_chars = row[1] or sum(c.char_count for c in chapters)
    encoding = row[2] or "utf-8"

    return SourceIndex(
        file_path=source_path,
        encoding=encoding,
        total_chars=total_chars,
        total_bytes=current_file_size,
        chapters=chapters,
    )


def _get_source_index() -> SourceIndex | None:
    """Get or build the source index (cached in module state).

    Tries three layers in order:
    1. In-memory cache (_source_index)
    2. Restore from DB chapter_index JSON (avoids re-scanning the file)
    3. Full file scan via index_source_novel()
    """
    global _source_index  # noqa: PLW0603

    if _source_index is not None:
        return _source_index

    source_path = _get_source_path()
    if source_path is None or not source_path.exists():
        return None

    # Try to restore from DB before doing a full file scan
    restored = _restore_index_from_db(source_path)
    if restored is not None:
        _source_index = restored
        return _source_index

    _source_index = index_source_novel(source_path)
    return _source_index


# ---------------------------------------------------------------------------
# Tool 1: Index source novel
# ---------------------------------------------------------------------------
@tool
def index_source() -> str:
    """建立源小说索引。扫描章节边界，生成目录。

    调用此工具后会得到：
    - 文件编码、总字符数
    - 章节目录（章节号、标题、字数）

    Returns:
        源小说目录信息。
    """
    source_path = _get_source_path()
    if source_path is None:
        return "错误：未找到源小说文件。请确保项目已正确初始化。"
    if not source_path.exists():
        return f"错误：源文件不存在: {source_path}"

    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    index = _get_source_index()
    if index is None:
        return "错误：无法建立索引。"

    # Save index metadata to database (include byte offsets for DB restoration)
    chapter_data = [
        {
            "id": ch.chapter_id,
            "title": ch.title,
            "chars": ch.char_count,
            "char_offset": ch.char_offset,
            "byte_offset": ch.byte_offset,
            "byte_count": ch.byte_count,
        }
        for ch in index.chapters
    ]
    with db._connection() as conn:
        conn.execute(
            "UPDATE imitate_source SET total_chars=?, total_chapters=?, encoding=?, chapter_index=? WHERE id=1",
            (
                index.total_chars,
                len(index.chapters),
                index.encoding,
                json.dumps(chapter_data, ensure_ascii=False),
            ),
        )

    # Build table of contents (show first 5 chapters only to save tokens)
    max_display = 5
    total = len(index.chapters)
    lines = [
        "源小说索引完成！",
        f"- 编码: {index.encoding}",
        f"- 总字符数: {index.total_chars:,}",
        f"- 检测到章节数: {total}",
        "",
        f"章节目录（前 {min(max_display, total)} 章）:",
    ]
    lines.extend(
        f"  {ch.chapter_id}. {ch.title} ({ch.char_count:,}字)"
        for ch in index.chapters[:max_display]
    )

    if total > max_display:
        lines.append(f"  ... 共 {total} 章，用 read_source_chapter(chapter=N) 按需逐章读取")

    if not index.chapters:
        lines.append("  （未检测到章节标记，可以用 read_source_range 按范围读取）")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: Read a specific chapter
# ---------------------------------------------------------------------------
@tool
def read_source_chapter(chapter: int) -> str:
    """读取源小说指定章节的原文。

    Args:
        chapter: 章节编号（从index_source获取）。

    Returns:
        该章节的完整原文。
    """
    source_path = _get_source_path()
    if source_path is None:
        return "错误：未找到源小说文件。"

    index = _get_source_index()
    if index is None:
        return "错误：请先调用 index_source() 建立索引。"

    if not index.chapters:
        return "错误：源小说没有检测到章节标记。请使用 read_source_range 按字符范围读取。"

    try:
        text = load_chapter_text(source_path, index, chapter)
    except ValueError as e:
        return f"错误：{e}"

    ch_info = next((c for c in index.chapters if c.chapter_id == chapter), None)
    title = ch_info.title if ch_info else f"第{chapter}章"
    char_count = ch_info.char_count if ch_info else len(text)
    return (
        f"=== {title} ({char_count:,}字) ===\n\n{text}\n\n"
        f"---\n"
        f"【精读要点】学习源文的写作技法（文风节奏、描写密度、人物刻画手法），\n"
        f"然后用原创文字写出质量优于原文的改编章节。\n"
        f"学源文的'怎么写'，不抄源文的'写了什么'。"
    )


# ---------------------------------------------------------------------------
# Tool 3: Read a range of chapters
# ---------------------------------------------------------------------------
@tool
def read_source_range(start_chapter: int, end_chapter: int) -> str:
    """读取源小说指定范围的章节原文。

    Args:
        start_chapter: 起始章节编号（含）。
        end_chapter: 结束章节编号（含）。

    Returns:
        指定范围章节的完整原文。
    """
    source_path = _get_source_path()
    if source_path is None:
        return "错误：未找到源小说文件。"

    index = _get_source_index()
    if index is None:
        return "错误：请先调用 index_source() 建立索引。"

    if not index.chapters:
        return "错误：源小说没有检测到章节标记。"

    try:
        text = load_chapter_range_text(source_path, index, start_chapter, end_chapter)
    except ValueError as e:
        return f"错误：{e}"

    total_chars = sum(
        c.char_count for c in index.chapters if start_chapter <= c.chapter_id <= end_chapter
    )
    return f"=== 第{start_chapter}-{end_chapter}章 ({total_chars:,}字) ===\n\n{text}"


# ---------------------------------------------------------------------------
# Tool 4: Search source text
# ---------------------------------------------------------------------------
@tool
def search_source(keyword: str, max_results: int = 10) -> str:
    """在源小说中搜索关键词，返回匹配段落及上下文。

    用于查找特定场景、角色出场、情节片段等。

    Args:
        keyword: 要搜索的关键词。
        max_results: 最多返回几条结果（默认10）。

    Returns:
        搜索结果及上下文。
    """
    source_path = _get_source_path()
    if source_path is None:
        return "错误：未找到源小说文件。"

    index = _get_source_index()
    if index is None:
        return "错误：请先调用 index_source() 建立索引。"

    results = search_source_text(source_path, index.encoding, keyword, max_results=max_results)

    if not results:
        return f"未找到包含 '{keyword}' 的内容。"

    lines = [f"搜索 '{keyword}' 找到 {len(results)} 处匹配：", ""]
    for i, (offset, snippet) in enumerate(results, 1):
        # Find which chapter this offset belongs to
        ch_label = "序章"
        for ch in index.chapters:
            if ch.char_offset <= offset < ch.char_offset + ch.char_count:
                ch_label = ch.title
                break
        lines.append(f"--- 匹配 {i} ({ch_label}) ---")
        lines.append(snippet)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5: Save analysis (flexible key-value)
# ---------------------------------------------------------------------------
@tool
def save_analysis(key: str, content: str) -> str:
    """保存分析结果。可以保存任何类型的分析：DNA分析、角色映射、改编计划等。

    常用key:
    - "dna_analysis": 源小说DNA分析（文风、结构、体系、情节骨架）
    - "character_mapping": 角色映射表
    - "power_system": 新金手指设计
    - "adaptation_plan": 章节级改编计划
    - "world_setting": 世界观设定
    - 其他自定义key

    Args:
        key: 分析结果的标识key。
        content: 分析内容（Markdown或JSON文本）。

    Returns:
        保存结果。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    with db._connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO imitate_analysis (key, content, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, content),
        )

    # Also export to analysis/ directory as markdown
    if _imitate_project_path is not None:
        analysis_dir = _imitate_project_path / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        safe_name = key.replace("/", "_").replace(" ", "_")
        export_file = analysis_dir / f"{safe_name}.md"
        export_file.write_text(f"# {key}\n\n{content}", encoding="utf-8")

    return f"分析结果 '{key}' 保存成功。（同时导出到 analysis/{key}.md）"


# ---------------------------------------------------------------------------
# Tool 6: Get analysis
# ---------------------------------------------------------------------------
@tool
def get_analysis(key: str) -> str:
    """获取已保存的分析结果。

    Args:
        key: 分析结果的标识key。

    Returns:
        分析内容，若不存在则返回提示。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    with db._connection() as conn:
        row = conn.execute("SELECT content FROM imitate_analysis WHERE key=?", (key,)).fetchone()

    if row is None:
        # List available keys
        with db._connection() as conn:
            keys = conn.execute("SELECT key FROM imitate_analysis ORDER BY key").fetchall()
        if keys:
            available = ", ".join(k[0] for k in keys)
            return f"未找到 '{key}'。已保存的分析: {available}"
        return f"未找到 '{key}'。尚未保存任何分析结果。"

    return row[0]


# ---------------------------------------------------------------------------
# Tool 7: Save generated chapter
# ---------------------------------------------------------------------------
@tool
def save_chapter(chapter: int, content: str, summary: str = "", title: str = "") -> str:
    """保存生成的章节内容和摘要。

    Args:
        chapter: 章节编号。
        content: 章节正文内容。
        summary: 章节摘要（用于后续章节的前文回顾）。如果省略，章节仍会保存，但请尽量提供。
        title: 章节标题（可选）。

    Returns:
        保存结果。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    with db._connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO imitate_chapters (chapter, title, content, summary) VALUES (?, ?, ?, ?)",
            (chapter, title, content, summary),
        )
        generated_count = conn.execute("SELECT COUNT(*) FROM imitate_chapters").fetchone()[0]

    # Save to filesystem
    if _imitate_project_path is not None:
        chapter_dir = _imitate_project_path / "chapters"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        chapter_file = chapter_dir / f"chapter-{chapter:03d}.md"
        header = f"# 第{chapter}章" + (f" {title}" if title else "") + "\n\n"
        chapter_file.write_text(header + content, encoding="utf-8")

    warning = ""
    if not summary:
        warning = "\n⚠️ 未提供章节摘要。请再调用一次 save_chapter 补充 summary，否则后续章节生成时缺少前文回顾。"

    return (
        f"第{chapter}章保存成功。已生成: {generated_count} 章{warning}\n\n"
        f"✅ 章节摘要已自动保存到数据库，后续章节的 get_generation_context 会自动获取。\n"
        f"→ 请直接向用户汇报完成情况，不需要再调用 remember、write_todos 等工具。"
    )


# ---------------------------------------------------------------------------
# Helper: extract chapter-specific plan from markdown
# ---------------------------------------------------------------------------
def _extract_chapter_plan(plan_text: str, chapter: int) -> str | None:
    """Extract chapter-specific adaptation plan from markdown text.

    Looks for sections like "第N章改编要点", "第N章", "章节N" etc.

    Args:
        plan_text: Full adaptation plan markdown.
        chapter: Chapter number to extract.

    Returns:
        Chapter-specific plan text, or None if not found.
    """
    # Try various heading patterns for this chapter
    # NOTE: Use string concat (not f-strings) for regex quantifiers like {1,4}
    # because f-strings interpret {1,4} as a Python set literal.
    patterns = [
        r"(#{1,4}\s*第" + str(chapter) + r"章[^\n]*\n)",
        r"(#{1,4}\s*Chapter\s*" + str(chapter) + r"[^\n]*\n)",
        r"(第" + str(chapter) + r"章改编要点[^\n]*\n)",
    ]

    for pattern in patterns:
        match = re.search(pattern, plan_text, re.IGNORECASE)
        if match:
            start = match.start()
            # Find next section heading at same or higher level
            heading_level = match.group().count("#")
            if heading_level > 0:
                next_pattern = r"^#{1," + str(heading_level) + r"}\s"
                next_heading = re.search(
                    next_pattern,
                    plan_text[match.end() :],
                    re.MULTILINE,
                )
            else:
                next_heading = re.search(
                    r"^#{1,4}\s|^第\d+章",
                    plan_text[match.end() :],
                    re.MULTILINE,
                )
            if next_heading:
                end = match.end() + next_heading.start()
            else:
                end = len(plan_text)
            return plan_text[start:end].strip()

    return None


# ---------------------------------------------------------------------------
# Tool 8: Get generation context
# ---------------------------------------------------------------------------
@tool
def get_generation_context(chapter: int) -> str:
    """获取指定章节的生成上下文。

    包括：源小说对应章节原文（作为风格参考）、改编计划、前文摘要。
    源小说原文是最重要的部分——Agent应直接模仿其文风来写。

    Args:
        chapter: 要生成的章节编号。

    Returns:
        生成该章节所需的完整上下文。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    parts = [f"=== 第{chapter}章 生成上下文 ==="]

    # 1. Source chapter text (THE KEY REFERENCE for style imitation)
    source_path = _get_source_path()
    index = _get_source_index()
    if source_path and index and index.chapters and chapter <= len(index.chapters):
        try:
            source_text = load_chapter_text(source_path, index, chapter)
            # Truncate if very long — keep enough text for style immersion
            max_ref_chars = 10000
            if len(source_text) > max_ref_chars:
                # Try to cut at a paragraph boundary
                cut_region = source_text[max_ref_chars - 500 : max_ref_chars]
                last_para = cut_region.rfind("\n\n")
                if last_para != -1:
                    cut_pos = max_ref_chars - 500 + last_para
                else:
                    cut_pos = max_ref_chars
                source_text = source_text[:cut_pos] + f"\n\n...(已截取前{cut_pos}字作为风格参考，原文共{len(source_text)}字)"
            parts.extend(["", f"## 源小说第{chapter}章原文（风格参考）", source_text])
        except ValueError:
            pass

    # 2. Adaptation plan for this chapter (if saved)
    with db._connection() as conn:
        row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='adaptation_plan'"
        ).fetchone()
    if row and row[0]:
        plan_text = row[0]
        # Extract chapter-specific section from markdown
        chapter_plan = _extract_chapter_plan(plan_text, chapter)
        if chapter_plan:
            parts.extend(["", "## 本章改编计划", chapter_plan])
        else:
            # Fallback: include full plan but truncated
            if len(plan_text) > 4000:
                plan_text = plan_text[:4000] + "\n\n...(改编计划已截取前4000字)"
            parts.extend(["", "## 改编计划（完整）", plan_text])

    # 3. Character mapping (for reference — truncate if very long)
    with db._connection() as conn:
        row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='character_mapping'"
        ).fetchone()
    if row and row[0]:
        mapping_text = row[0]
        if len(mapping_text) > 3000:
            mapping_text = mapping_text[:3000] + "\n\n...(角色映射已截取前3000字，完整版用 get_analysis('character_mapping') 查看)"
        parts.extend(["", "## 角色映射", mapping_text])

    # 4. Power system (for reference)
    with db._connection() as conn:
        row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='power_system'"
        ).fetchone()
    if row and row[0]:
        parts.extend(["", "## 金手指设定", row[0]])

    # 4b. World atmosphere (for genre/style consistency)
    with db._connection() as conn:
        row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='world_atmosphere'"
        ).fetchone()
    if row and row[0]:
        parts.extend(["", "## 题材氛围DNA", row[0]])

    # 5. Previous chapter summaries (last 3)
    with db._connection() as conn:
        rows = conn.execute(
            "SELECT chapter, title, summary FROM imitate_chapters WHERE chapter < ? ORDER BY chapter DESC LIMIT 3",
            (chapter,),
        ).fetchall()
    if rows:
        parts.extend(["", "## 前文摘要"])
        for r in reversed(rows):
            title_part = f"《{r[1]}》" if r[1] else ""
            parts.append(f"- 第{r[0]}章{title_part}: {r[2]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 9: Get project status
# ---------------------------------------------------------------------------
@tool
def get_project_status() -> str:
    """获取仿写项目完整状态。

    Returns:
        项目状态报告：源小说信息、已保存的分析、已生成的章节。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    lines = ["=== 仿写项目状态 ==="]

    # Source info
    with db._connection() as conn:
        row = conn.execute(
            "SELECT file_path, total_chars, total_chapters, encoding FROM imitate_source WHERE id=1"
        ).fetchone()
    if row:
        lines.extend(
            [
                "",
                "源小说:",
                f"  文件: {row[0]}",
                f"  字符数: {row[1]:,}" if row[1] else "  字符数: 未扫描",
                f"  章节数: {row[2]}" if row[2] else "  章节数: 未扫描",
                f"  编码: {row[3]}" if row[3] else "  编码: 未检测",
            ]
        )

    # Saved analyses
    with db._connection() as conn:
        analysis_rows = conn.execute(
            "SELECT key, LENGTH(content), updated_at FROM imitate_analysis ORDER BY key"
        ).fetchall()
    if analysis_rows:
        lines.extend(["", "已保存的分析:"])
        lines.extend(f"  - {r[0]} ({r[1]:,}字) [{r[2]}]" for r in analysis_rows)
    else:
        lines.extend(["", "已保存的分析: （无）"])

    # Generated chapters
    with db._connection() as conn:
        chapter_rows = conn.execute(
            "SELECT chapter, title FROM imitate_chapters ORDER BY chapter"
        ).fetchall()
    if chapter_rows:
        lines.extend(["", f"已生成章节: {len(chapter_rows)} 章"])
        for r in chapter_rows:
            title_part = f" {r[1]}" if r[1] else ""
            lines.append(f"  - 第{r[0]}章{title_part}")
    else:
        lines.extend(["", "已生成章节: （无）"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Project initialization helper
# ---------------------------------------------------------------------------
def setup_imitate_project(
    project_path: Path,
    source_file: Path,
    title: str,
) -> None:
    """Set up a new imitation project.

    Args:
        project_path: Path to the new project directory.
        source_file: Path to the source novel file.
        title: Project title.
    """
    for subdir in ("source", "analysis", "world", "outline", "chapters", "output"):
        (project_path / subdir).mkdir(parents=True, exist_ok=True)

    # Copy source file
    dest = project_path / "source" / source_file.name
    shutil.copy2(source_file, dest)

    # Initialize database
    init_imitate_store(project_path)

    db = _get_db()
    if db is None:
        msg = "Failed to initialize database"
        raise RuntimeError(msg)

    # Record source metadata
    file_size = source_file.stat().st_size
    rel_path = f"source/{source_file.name}"
    with db._connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO imitate_source (id, file_path, file_size) VALUES (1, ?, ?)",
            (rel_path, file_size),
        )


# ---------------------------------------------------------------------------
# Tool export
# ---------------------------------------------------------------------------
def get_all_imitate_tools() -> list:
    """Get all imitation-related tools.

    Returns:
        List of all tool functions for the imitation workflow.
    """
    return [
        index_source,
        read_source_chapter,
        read_source_range,
        search_source,
        save_analysis,
        get_analysis,
        save_chapter,
        get_generation_context,
        get_project_status,
    ]
