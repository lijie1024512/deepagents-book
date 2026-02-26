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

-- Character evolution tracking (per-chapter updates)
CREATE TABLE IF NOT EXISTS imitate_character_evolution (
    character_name TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    changes TEXT NOT NULL,
    personality_shift TEXT DEFAULT '',
    relationship_changes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (character_name, chapter)
);

-- Golden finger / power system evolution (per-chapter)
CREATE TABLE IF NOT EXISTS imitate_power_evolution (
    chapter INTEGER PRIMARY KEY,
    ability_unlocked TEXT DEFAULT '',
    limitation_discovered TEXT DEFAULT '',
    usage_context TEXT DEFAULT '',
    evolution_note TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Creative deviation log (records each creative choice)
CREATE TABLE IF NOT EXISTS imitate_creative_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    category TEXT NOT NULL,
    source_original TEXT DEFAULT '',
    adapted_version TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- User feedback skill library (experience distillation)
CREATE TABLE IF NOT EXISTS imitate_skill_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    skill_type TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source_feedback TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Technique terms — used for preference tracking in innovation prompts
# ---------------------------------------------------------------------------
_TECHNIQUE_TERMS = frozenset(
    {
        "五感交织",
        "以小见大",
        "白描速写",
        "工笔细描",
        "感官联觉",
        "环境映射情绪",
        "动态静物",
        "动作性格化",
        "对话潜台词",
        "细节暗示",
        "反差设定",
        "台词标签",
        "镜像对比",
        "行为弧光",
        "先声夺人",
        "悬念前置",
        "场景即入",
        "倒叙切入",
        "内心独白开场",
        "欲扬先抑",
        "快进慢写",
        "断崖悬停",
        "节奏变速",
        "压抑-释放循环",
        "三段递进",
        "信息差碾压",
        "扮猪吃虎",
        "步步升级",
        "打脸反转",
        "底牌揭示",
        "鉴宝慧眼",
        "以弱胜强",
        "切幕悬停",
        "答案延迟",
        "悬念递进",
        "草蛇灰线",
        "误导与反转",
    }
)


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
        f"{'=' * 60}\n"
        f"⚠️ 以下源文仅供学习写作技法，严禁复制任何原文句子！\n"
        f"{'=' * 60}\n\n"
        f"=== {title} ({char_count:,}字) ===\n\n{text}\n\n"
        f"{'=' * 60}\n"
        f"⚠️ 仿写铁律（违反任何一条都是抄袭）：\n"
        f"1. 禁止复制源文的句子——哪怕只是换个人名也是抄袭\n"
        f"2. 禁止照搬源文的场景顺序——你必须按【改编计划】的场景来写\n"
        f"3. 禁止使用源文的描写原句——你要用改编计划里的新世界观元素重新描写\n"
        f"4. 源文只是技法老师：学它的描写密度、文风节奏、刻画手法\n"
        f"5. 你的内容必须来自改编计划：新角色、新金手指、新剧情事件\n"
        f"6. 青出于蓝胜于蓝：源文N个描写维度，你要N+1个维度，质量必须超越源文\n"
        f"{'=' * 60}"
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
def _strip_markdown_formatting(text: str) -> str:
    """Strip markdown inline formatting from text for clean Word output.

    Removes bold (**text** / __text__), italic (*text* / _text_),
    and bold-italic (***text***) markers while preserving the inner text.

    Args:
        text: The text to clean.

    Returns:
        Text with markdown inline formatting removed.
    """
    import re

    # Bold-italic (***text*** or ___text___)
    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)
    text = re.sub(r"_{3}(.+?)_{3}", r"\1", text)
    # Bold (**text** or __text__)
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)
    text = re.sub(r"_{2}(.+?)_{2}", r"\1", text)
    # Italic (*text*) — avoid matching math like 2*3
    text = re.sub(r"(?<![0-9*])\*([^\s*][^*]*?[^\s*])\*(?![0-9*])", r"\1", text)
    return re.sub(r"(?<![0-9*])\*([^\s*])\*(?![0-9*])", r"\1", text)


@tool
def save_chapter(chapter: int, content: str, summary: str = "", title: str = "") -> str:
    """保存生成的章节内容和摘要。必须一次性提供content和summary，不要分两次调用。

    Args:
        chapter: 章节编号。
        content: 章节正文内容（纯文本，不含Markdown格式符号）。
        summary: 章节摘要（80-200字，用于后续章节的前文回顾和历史系统）。
            应包含：1) 主要剧情事件 2) 角色关键变化 3) 金手指使用/演化 4) 关键伏笔或悬念。
            请务必一次性提供，不要省略。
        title: 章节标题（可选）。

    Returns:
        保存结果。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    # Strip any markdown formatting for clean Word-compatible output
    content = _strip_markdown_formatting(content)

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
        header = f"第{chapter}章" + (f" {title}" if title else "") + "\n\n"
        chapter_file.write_text(header + content, encoding="utf-8")

    summary_note = ""
    if not summary:
        summary_note = "\n⚠️ 未提供摘要！后续章节前文回顾和历史记录将不完整。请重新调用 save_chapter 并提供 summary（80-200字，含：主要事件+角色变化+金手指状态+伏笔）。"
    elif len(summary) < 30:
        summary_note = f"\n⚠️ 摘要仅{len(summary)}字，过于简短。建议80-200字，需包含：主要事件+角色变化+金手指状态+伏笔。"
    elif len(summary) > 500:
        summary_note = f"\n💡 摘要{len(summary)}字，建议精简到200字以内以节省上下文空间。"

    return (
        f"第{chapter}章保存成功（{len(content)}字）。已生成: {generated_count} 章。{summary_note}\n"
        f"→ 接下来请记录本章创新（推荐），然后向用户汇报：\n"
        f"  - evolve_character(...) — 角色在本章有什么变化？\n"
        f"  - evolve_golden_finger(...) — 金手指有演化吗？\n"
        f"  - log_creative_choice(...) — 做了哪些创意偏离？\n"
        f"  记录完毕后直接向用户汇报，不要再调用其他工具。"
    )


# ---------------------------------------------------------------------------
# Tool 10: Evolve character
# ---------------------------------------------------------------------------
@tool
def evolve_character(
    character_name: str,
    chapter: int,
    changes: str,
    personality_shift: str = "",
    relationship_changes: str = "",
) -> str:
    """记录角色在本章的成长和变化。

    每章写完后调用，追踪角色如何从源角色逐步偏离、成长。
    这些记录会在后续章节的 get_generation_context 中自动注入。

    Args:
        character_name: 角色名（使用改编后的名字）。
        chapter: 章节编号。
        changes: 本章发生了什么变化（行为、决策、经历）。
        personality_shift: 性格偏移描述（如"从被动转向主动"）。
        relationship_changes: 与其他角色的关系变化。

    Returns:
        保存结果。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    with db._connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO imitate_character_evolution "
            "(character_name, chapter, changes, personality_shift, relationship_changes) "
            "VALUES (?, ?, ?, ?, ?)",
            (character_name, chapter, changes, personality_shift, relationship_changes),
        )

    return f"角色 [{character_name}] 第{chapter}章演化已记录。"


# ---------------------------------------------------------------------------
# Tool 11: Evolve golden finger / power system
# ---------------------------------------------------------------------------
@tool
def evolve_golden_finger(
    chapter: int,
    ability_unlocked: str = "",
    limitation_discovered: str = "",
    usage_context: str = "",
    evolution_note: str = "",
) -> str:
    """记录金手指在本章的演化。

    追踪金手指如何从初始设计逐步成长：解锁新能力、发现新限制、新用法。
    后续章节会自动看到完整的演化轨迹。

    Args:
        chapter: 章节编号。
        ability_unlocked: 本章解锁/展示了什么能力。
        limitation_discovered: 发现了什么限制或代价。
        usage_context: 在什么情境下使用了金手指。
        evolution_note: 相比上一次使用有什么变化。

    Returns:
        保存结果。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    with db._connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO imitate_power_evolution "
            "(chapter, ability_unlocked, limitation_discovered, usage_context, evolution_note) "
            "VALUES (?, ?, ?, ?, ?)",
            (chapter, ability_unlocked, limitation_discovered, usage_context, evolution_note),
        )

    return f"金手指第{chapter}章演化已记录。"


# ---------------------------------------------------------------------------
# Tool 12: Log creative choice
# ---------------------------------------------------------------------------
@tool
def log_creative_choice(
    chapter: int,
    category: str,
    source_original: str,
    adapted_version: str,
    reason: str = "",
) -> str:
    """记录一个创意偏离决策。

    追踪改编与源文的偏离方向和程度，帮助保持创新一致性。
    后续章节会基于偏离模式生成创新提示。

    Args:
        chapter: 章节编号。
        category: 偏离类别 - "plot"(情节) / "character"(角色) / "golden_finger"(金手指) / "setting"(设定)。
        source_original: 源文中原来是什么。
        adapted_version: 改编成了什么。
        reason: 为什么这么改（可选）。

    Returns:
        保存结果。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    valid_categories = {"plot", "character", "golden_finger", "setting"}
    if category not in valid_categories:
        return f"错误：category 必须是 {valid_categories} 之一，收到 '{category}'"

    with db._connection() as conn:
        conn.execute(
            "INSERT INTO imitate_creative_log "
            "(chapter, category, source_original, adapted_version, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (chapter, category, source_original, adapted_version, reason),
        )

    return f"创意偏离已记录：[{category}] 第{chapter}章。"


# ---------------------------------------------------------------------------
# Tool: Record writing skill (user feedback distillation)
# ---------------------------------------------------------------------------
@tool
def record_writing_skill(
    chapter: int,
    skill_type: str,
    category: str,
    content: str,
    source_feedback: str = "",
) -> str:
    """记录用户反馈蒸馏的写作经验。

    将用户对章节的反馈蒸馏为可复用的成功模式或经验教训，
    自动注入后续章节的生成上下文。

    Args:
        chapter: 章节编号。
        skill_type: 经验类型，"success_pattern"（成功模式）或 "lesson_learned"（经验教训）。
        category: 经验分类：direction/writing/golden_finger/character/pacing/description。
        content: 一句话描述经验内容（最多200字）。
        source_feedback: 用户原始反馈（可选）。

    Returns:
        确认消息。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    valid_skill_types = {"success_pattern", "lesson_learned"}
    if skill_type not in valid_skill_types:
        return f"错误：skill_type 必须是 {valid_skill_types} 之一，收到 '{skill_type}'"

    valid_categories = {
        "direction",
        "writing",
        "golden_finger",
        "character",
        "pacing",
        "description",
    }
    if category not in valid_categories:
        return f"错误：category 必须是 {valid_categories} 之一，收到 '{category}'"

    # Truncate content to 200 chars
    content = content[:200]

    with db._connection() as conn:
        conn.execute(
            "INSERT INTO imitate_skill_library "
            "(chapter, skill_type, category, content, source_feedback) "
            "VALUES (?, ?, ?, ?, ?)",
            (chapter, skill_type, category, content, source_feedback),
        )

    type_label = "成功模式" if skill_type == "success_pattern" else "经验教训"
    return f"写作经验已记录：[{type_label}/{category}] 第{chapter}章 — {content[:50]}"


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
            end = match.end() + next_heading.start() if next_heading else len(plan_text)
            return plan_text[start:end].strip()

    return None


# ---------------------------------------------------------------------------
# Tool 8: Get generation context
# ---------------------------------------------------------------------------
def _build_sliding_summary(db: NovelDatabase, current_chapter: int) -> str:
    """Build a sliding window summary for previous chapters.

    For chapters 1-4: list all previous summaries directly.
    For chapter 5+: compress older chapters into a global summary + last 3 detailed.

    Args:
        db: Database instance.
        current_chapter: The chapter being generated.

    Returns:
        Formatted summary string.
    """
    with db._connection() as conn:
        all_rows = conn.execute(
            "SELECT chapter, title, summary FROM imitate_chapters WHERE chapter < ? ORDER BY chapter",
            (current_chapter,),
        ).fetchall()

    if not all_rows:
        return ""

    if len(all_rows) <= 4:
        # Few chapters — list all
        lines = []
        for r in all_rows:
            title_part = f"《{r[1]}》" if r[1] else ""
            lines.append(f"- 第{r[0]}章{title_part}: {r[2]}")
        return "\n".join(lines)

    # 5+ chapters: global summary of older chapters + last 3 detailed
    older = all_rows[:-3]
    recent = all_rows[-3:]

    # Compress older chapters into a brief summary
    older_lines = []
    for r in older:
        title_part = f"《{r[1]}》" if r[1] else ""
        older_lines.append(f"第{r[0]}章{title_part}: {r[2]}")
    global_summary = " → ".join(
        f"第{r[0]}章({r[2][:30]}...)" if len(r[2] or "") > 30 else f"第{r[0]}章({r[2]})"
        for r in older
    )

    lines = [f"【全局脉络】{global_summary}", "", "【近章摘要】"]
    for r in recent:
        title_part = f"《{r[1]}》" if r[1] else ""
        lines.append(f"- 第{r[0]}章{title_part}: {r[2]}")

    return "\n".join(lines)


def _extract_relevant_characters(chapter_plan: str | None, full_mapping: str) -> str:
    """Extract only characters mentioned in the chapter plan.

    If chapter_plan is available, filters the character mapping to only include
    characters whose names appear in the plan. Falls back to full mapping
    (truncated) if no plan is available.

    Args:
        chapter_plan: The chapter-specific adaptation plan text.
        full_mapping: The complete character mapping text.

    Returns:
        Filtered or truncated character mapping.
    """
    if not chapter_plan or not full_mapping:
        if len(full_mapping) > 2000:
            return (
                full_mapping[:2000]
                + "\n...(已截取，完整版用 get_analysis('character_mapping') 查看)"
            )
        return full_mapping

    # Extract character names from mapping (look for patterns like "→ 新名字" or "名字：")
    lines = full_mapping.split("\n")
    relevant_lines: list[str] = []
    current_section: list[str] = []
    section_relevant = False

    for line in lines:
        # Detect section headers or character entries
        stripped = line.strip()
        if stripped.startswith(("#", "---")):
            # Flush previous section if relevant
            if section_relevant and current_section:
                relevant_lines.extend(current_section)
            current_section = [line]
            section_relevant = False
            continue

        current_section.append(line)
        # Check if any word from this line appears in the chapter plan
        # This catches character names mentioned in the plan
        words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}", stripped)
        for word in words:
            if word in chapter_plan and len(word) >= 2:
                section_relevant = True
                break

    # Flush last section
    if section_relevant and current_section:
        relevant_lines.extend(current_section)

    if relevant_lines:
        result = "\n".join(relevant_lines)
        if len(result) > 2000:
            result = result[:2000] + "\n...(已截取)"
        return result

    # Fallback: return truncated full mapping
    if len(full_mapping) > 2000:
        return (
            full_mapping[:2000] + "\n...(已截取，完整版用 get_analysis('character_mapping') 查看)"
        )
    return full_mapping


def _build_innovation_prompt(db: NovelDatabase, chapter: int, chapter_plan: str | None) -> str:
    """Generate an innovation prompt based on recent creative patterns.

    Analyzes the creative_log to identify which categories have been
    innovated on and which need more attention.

    Args:
        db: Database instance.
        chapter: Current chapter number.
        chapter_plan: Chapter-specific plan text.

    Returns:
        Innovation prompt string, or empty string if no prior data.
    """
    with db._connection() as conn:
        # Get creative log from recent chapters
        logs = conn.execute(
            "SELECT chapter, category, source_original, adapted_version "
            "FROM imitate_creative_log WHERE chapter >= ? ORDER BY chapter",
            (max(1, chapter - 5),),
        ).fetchall()

        # Get character evolution to see who's been developing
        char_evolutions = conn.execute(
            "SELECT character_name, chapter, changes FROM imitate_character_evolution "
            "WHERE chapter >= ? ORDER BY chapter DESC",
            (max(1, chapter - 3),),
        ).fetchall()

        # Get power evolution to check golden finger progression
        power_evos = conn.execute(
            "SELECT chapter, ability_unlocked, evolution_note FROM imitate_power_evolution "
            "ORDER BY chapter DESC LIMIT 3"
        ).fetchall()

    if not logs and not char_evolutions and not power_evos:
        return ""

    parts = ["## 创新提示"]

    # Analyze category distribution
    if logs:
        category_counts: dict[str, int] = {}
        for _, cat, _, _ in logs:
            category_counts[cat] = category_counts.get(cat, 0) + 1

        total = sum(category_counts.values())
        if total > 0:
            dist_parts = []
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                cat_cn = {
                    "plot": "情节",
                    "character": "角色",
                    "golden_finger": "金手指",
                    "setting": "设定",
                }.get(cat, cat)
                pct = round(count / total * 100)
                dist_parts.append(f"{cat_cn}{pct}%")
            parts.append(f"前几章创意偏离分布：{'、'.join(dist_parts)}")

            # Suggest underrepresented categories
            all_cats = {"plot", "character", "golden_finger", "setting"}
            missing = all_cats - set(category_counts.keys())
            low_cats = {c for c, n in category_counts.items() if n / total < 0.15}
            suggest_cats = missing | low_cats
            if suggest_cats:
                suggest_cn = [
                    {
                        "plot": "情节",
                        "character": "角色",
                        "golden_finger": "金手指",
                        "setting": "设定",
                    }.get(c, c)
                    for c in suggest_cats
                ]
                parts.append(f"建议本章加强：{'、'.join(suggest_cn)}方面的创新")

    # Check golden finger staleness
    if power_evos:
        last_power_chapter = power_evos[0][0]
        gap = chapter - last_power_chapter
        if gap >= 3:
            parts.append(f"金手指已经 {gap} 章没有演化，考虑在本章展示新能力或发现新限制")
    elif chapter > 2:
        parts.append("金手指尚未有演化记录，考虑在本章开始追踪其成长")

    # Character development hints
    if char_evolutions and chapter_plan:
        recent_chars = {ce[0] for ce in char_evolutions}
        if recent_chars:
            parts.append(f"近期有演化记录的角色：{'、'.join(list(recent_chars)[:5])}")

    # Technique preference tracking (from skill library)
    try:
        with db._connection() as conn:
            skill_rows = conn.execute(
                "SELECT content FROM imitate_skill_library "
                "WHERE skill_type='success_pattern' "
                "AND category IN ('writing', 'description', 'pacing')"
            ).fetchall()
        if skill_rows:
            term_counts: dict[str, int] = {}
            for (text,) in skill_rows:
                for term in _TECHNIQUE_TERMS:
                    if term in text:
                        term_counts[term] = term_counts.get(term, 0) + 1
            preferred = [t for t, c in term_counts.items() if c >= 2]
            if preferred:
                parts.append(f"用户偏好技法：{'、'.join(preferred[:8])}")
    except Exception:  # noqa: BLE001, S110
        pass  # Table may not exist in older databases

    return "\n".join(parts) if len(parts) > 1 else ""


def _build_skill_library_prompt(db: NovelDatabase, chapter: int) -> str:
    """Build a skill library prompt from user feedback distillation.

    Queries the imitate_skill_library for recent success patterns and
    lesson learned entries, formatted as a compact markdown section.

    Args:
        db: Database instance.
        chapter: Current chapter number (unused but kept for future filtering).

    Returns:
        Formatted skill library prompt, or empty string if no entries.
    """
    try:
        with db._connection() as conn:
            successes = conn.execute(
                "SELECT chapter, category, content FROM imitate_skill_library "
                "WHERE skill_type='success_pattern' "
                "ORDER BY id DESC LIMIT 10"
            ).fetchall()
            lessons = conn.execute(
                "SELECT chapter, category, content FROM imitate_skill_library "
                "WHERE skill_type='lesson_learned' "
                "ORDER BY id DESC LIMIT 5"
            ).fetchall()
    except Exception:  # noqa: BLE001
        return ""  # Table may not exist in older databases

    if not successes and not lessons:
        return ""

    parts = ["## 写作经验库（用户反馈蒸馏）"]

    if successes:
        parts.append("\n**成功模式**（复用这些写法）：")
        for ch, cat, text in successes:
            parts.append(f"- [第{ch}章/{cat}] {text}")

    if lessons:
        parts.append("\n**经验教训**（避免这些问题）：")
        for ch, cat, text in lessons:
            parts.append(f"- [第{ch}章/{cat}] {text}")

    return "\n".join(parts)


@tool
def get_generation_context(chapter: int) -> str:
    """获取指定章节的生成上下文。

    包括：改编计划、本章涉及角色（含演化轨迹）、金手指当前状态（含演化历史）、
    前文脉络（滑动窗口）、创新提示。
    不包含源文原文（已通过 read_source_chapter 单独阅读，避免重复占用 token）。

    Args:
        chapter: 要生成的章节编号。

    Returns:
        生成该章节所需的完整上下文。
    """
    db = _get_db()
    if db is None:
        return "错误：无法访问数据库。"

    parts = [f"=== 第{chapter}章 生成上下文 ==="]

    # 1. Chapter-specific adaptation plan (highest priority, shown first)
    chapter_plan: str | None = None
    with db._connection() as conn:
        row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='adaptation_plan'"
        ).fetchone()
    if row and row[0]:
        plan_text = row[0]
        chapter_plan = _extract_chapter_plan(plan_text, chapter)
        if chapter_plan:
            parts.extend(["", "## 本章改编计划（核心目标）", chapter_plan])
        else:
            if len(plan_text) > 4000:
                plan_text = plan_text[:4000] + "\n\n...(改编计划已截取前4000字)"
            parts.extend(["", "## 改编计划（完整）", plan_text])

    # 2. Relevant characters + evolution trajectory
    with db._connection() as conn:
        mapping_row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='character_mapping'"
        ).fetchone()
    if mapping_row and mapping_row[0]:
        relevant_mapping = _extract_relevant_characters(chapter_plan, mapping_row[0])
        parts.extend(["", "## 本章涉及角色", relevant_mapping])

        # Append character evolution history
        with db._connection() as conn:
            char_evos = conn.execute(
                "SELECT character_name, chapter, changes, personality_shift, relationship_changes "
                "FROM imitate_character_evolution ORDER BY chapter"
            ).fetchall()
        if char_evos:
            evo_lines = ["", "### 角色演化轨迹"]
            current_char = ""
            for name, ch, changes, personality, relationships in char_evos:
                if name != current_char:
                    current_char = name
                    evo_lines.append(f"\n**{name}**:")
                evo_parts_inner = [f"  - 第{ch}章: {changes}"]
                if personality:
                    evo_parts_inner.append(f"    性格偏移: {personality}")
                if relationships:
                    evo_parts_inner.append(f"    关系变化: {relationships}")
                evo_lines.extend(evo_parts_inner)
            parts.extend(evo_lines)

    # 3. Golden finger: base design + evolution history (alive, not static)
    with db._connection() as conn:
        power_row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='power_system'"
        ).fetchone()
    if power_row and power_row[0]:
        power_text = power_row[0]
        # Compress base design if very long
        if len(power_text) > 1500:
            power_text = (
                power_text[:1500]
                + "\n...(基础设计已压缩，完整版用 get_analysis('power_system') 查看)"
            )
        parts.extend(["", "## 金手指", "### 基础设计", power_text])

        # Append evolution history
        with db._connection() as conn:
            power_evos = conn.execute(
                "SELECT chapter, ability_unlocked, limitation_discovered, usage_context, evolution_note "
                "FROM imitate_power_evolution ORDER BY chapter"
            ).fetchall()
        if power_evos:
            parts.append("\n### 演化历程")
            for ch, ability, limitation, context, note in power_evos:
                evo_line = f"- 第{ch}章:"
                if ability:
                    evo_line += f" 【能力】{ability}"
                if limitation:
                    evo_line += f" 【限制】{limitation}"
                if context:
                    evo_line += f" 【情境】{context}"
                if note:
                    evo_line += f" 【变化】{note}"
                parts.append(evo_line)

            # Show current state summary
            latest = power_evos[-1]
            parts.append(f"\n当前状态（第{latest[0]}章后）：已解锁能力 {len(power_evos)} 次演化")

    # 4. World atmosphere (compressed to key points)
    with db._connection() as conn:
        atmo_row = conn.execute(
            "SELECT content FROM imitate_analysis WHERE key='world_atmosphere'"
        ).fetchone()
    if atmo_row and atmo_row[0]:
        atmo_text = atmo_row[0]
        if len(atmo_text) > 1000:
            atmo_text = atmo_text[:1000] + "\n...(完整版用 get_analysis('world_atmosphere') 查看)"
        parts.extend(["", "## 氛围速查", atmo_text])

    # 5. Sliding window summary (global + recent 3)
    summary_text = _build_sliding_summary(db, chapter)
    if summary_text:
        parts.extend(["", "## 前文脉络", summary_text])

    # 6. Skill library (user feedback distillation)
    skill_prompt = _build_skill_library_prompt(db, chapter)
    if skill_prompt:
        parts.extend(["", skill_prompt])

    # 7. Innovation prompt (based on creative log analysis)
    innovation_prompt = _build_innovation_prompt(db, chapter, chapter_plan)
    if innovation_prompt:
        parts.extend(["", innovation_prompt])

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
        evolve_character,
        evolve_golden_finger,
        log_creative_choice,
        record_writing_skill,
    ]
