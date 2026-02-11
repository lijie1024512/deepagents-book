"""Novel Writing Hooks System.

Inspired by planning-with-files project, this module implements automatic hooks
that trigger before/after tool calls to maintain context consistency.

Key Hooks:
1. PreToolUse: Auto-read relevant context before write operations
2. PostToolUse: Remind to update progress/check foreshadows after chapter completion
3. Auto-checkpoint: Create checkpoints after significant operations
4. Session Recovery: Check pending operations and provide recovery context

Design Philosophy (from planning-with-files):
- "Context Window = RAM (volatile), Filesystem = Disk (persistent)"
- 2-Action Rule: After every 2 view/browser/search operations, save findings
- 5-Question Reboot Check: Session recovery context verification
"""

from __future__ import annotations

import functools
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from deepagents_cli.novel.database import NovelDatabase
    from deepagents_cli.novel.project import NovelProject

# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])

# Global state for hook tracking
_hook_state: dict[str, Any] = {
    "operation_count": 0,  # Track operations for 2-action rule
    "checkpoint_threshold": 3,  # Auto-checkpoint every N significant operations
    "last_checkpoint": None,  # Last checkpoint time
    "pending_reminders": [],  # Reminders to inject into next response
    "session_start": None,  # Session start time
    "project_path": None,  # Current project path
}


def init_hooks(project_path: Path) -> None:
    """Initialize hooks for a novel project.

    Args:
        project_path: Path to the novel project
    """
    global _hook_state
    _hook_state["project_path"] = project_path
    _hook_state["session_start"] = datetime.now().isoformat()
    _hook_state["operation_count"] = 0
    _hook_state["pending_reminders"] = []


def _get_project() -> "NovelProject | None":
    """Get the current project instance."""
    project_path = _hook_state.get("project_path")
    if project_path is None:
        return None

    from deepagents_cli.novel.project import NovelProject

    try:
        return NovelProject.load(project_path)
    except (FileNotFoundError, Exception):
        return None


def _get_db() -> "NovelDatabase | None":
    """Get the database instance if available.

    This function can work even without a full project config,
    as long as the database file exists.
    """
    project_path = _hook_state.get("project_path")
    if project_path is None:
        return None

    # Try to get from project first
    project = _get_project()
    if project and project.uses_sqlite:
        return project.db

    # Fallback: directly check for database file
    db_file = project_path / ".novel" / "novel.db"
    if db_file.exists():
        from deepagents_cli.novel.database import NovelDatabase

        return NovelDatabase(project_path)

    return None


# =============================================================================
# Pre-Tool Hooks
# =============================================================================


def _pre_write_chapter_hook(chapter: int) -> str | None:
    """Hook that runs before writing a chapter.

    Automatically gathers relevant context:
    - Previous chapter summary
    - Current chapter outline (if exists)
    - Active characters in recent chapters
    - Pending foreshadows that might need attention

    Returns:
        Context string to be prepended, or None if no context needed
    """
    db = _get_db()
    if db is None:
        return None

    context_parts = []

    # 1. Get previous chapter summary
    progress = db.get_progress()
    current_chapter = progress.get("current_chapter", 1)
    last_summary = progress.get("last_chapter_summary")

    if last_summary:
        context_parts.append(f"【上一章摘要】(第{current_chapter - 1}章)")
        context_parts.append(last_summary[:500])
        context_parts.append("")

    # 2. Check for chapter outline
    project = _get_project()
    if project:
        volume = (chapter - 1) // 50 + 1
        outline_file = project.path / "outline" / f"volume-{volume}" / f"chapter-{chapter:03d}.md"
        if outline_file.exists():
            outline_content = outline_file.read_text(encoding="utf-8")
            context_parts.append(f"【第{chapter}章大纲】")
            # Truncate if too long
            if len(outline_content) > 1000:
                outline_content = outline_content[:1000] + "..."
            context_parts.append(outline_content)
            context_parts.append("")

    # 3. Get active characters (appeared in last 3 chapters)
    characters = db.list_characters()
    recent_chars = [c for c in characters if c.get("last_appearance", 0) >= current_chapter - 3]
    if recent_chars:
        context_parts.append("【近期活跃角色】")
        for char in recent_chars[:5]:
            context_parts.append(
                f"- {char['name']}: {char.get('status', '?')}, 位置: {char.get('location', '?')}"
            )
        context_parts.append("")

    # 4. Check pending foreshadows that might need resolution
    foreshadows = db.list_foreshadows(include_resolved=False)
    relevant_fs = [
        f for f in foreshadows if f.get("target_chapter") and f["target_chapter"] <= chapter + 5
    ]
    if relevant_fs:
        context_parts.append("【临近回收的伏笔】")
        for fs in relevant_fs[:3]:
            context_parts.append(f"- {fs.get('name', '?')}: 预计第{fs.get('target_chapter')}章回收")
        context_parts.append("")

    if context_parts:
        return "\n".join(context_parts)
    return None


def _pre_outline_hook(chapter: int) -> str | None:
    """Hook that runs before writing an outline.

    Gathers context for outline writing:
    - Story framework summary
    - Previous chapter outline
    - Character recruitment status
    - Major plot threads

    Returns:
        Context string or None
    """
    db = _get_db()
    project = _get_project()
    if db is None or project is None:
        return None

    context_parts = []

    # 1. Check for story framework
    framework_file = project.path / "outline" / "story-framework.md"
    if framework_file.exists():
        framework = framework_file.read_text(encoding="utf-8")
        context_parts.append("【整体框架】")
        # Extract key sections (first 500 chars)
        if len(framework) > 500:
            framework = framework[:500] + "..."
        context_parts.append(framework)
        context_parts.append("")

    # 2. Get previous chapter outline
    if chapter > 1:
        volume = (chapter - 2) // 50 + 1
        prev_outline = (
            project.path / "outline" / f"volume-{volume}" / f"chapter-{chapter - 1:03d}.md"
        )
        if prev_outline.exists():
            prev_content = prev_outline.read_text(encoding="utf-8")
            context_parts.append(f"【第{chapter - 1}章大纲】")
            if len(prev_content) > 500:
                prev_content = prev_content[:500] + "..."
            context_parts.append(prev_content)
            context_parts.append("")

    # 3. Character status overview
    characters = db.list_characters()
    if characters:
        by_status: dict[str, list[str]] = {}
        for c in characters:
            status = c.get("status", "未出场")
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(c["name"])

        context_parts.append("【角色状态概览】")
        for status, names in by_status.items():
            context_parts.append(
                f"- {status}: {', '.join(names[:5])}"
                + (f" 等{len(names)}人" if len(names) > 5 else "")
            )
        context_parts.append("")

    # 4. Pending foreshadows
    foreshadows = db.list_foreshadows(include_resolved=False)
    if foreshadows:
        context_parts.append(f"【待回收伏笔】({len(foreshadows)}个)")
        for fs in foreshadows[:5]:
            context_parts.append(
                f"- {fs.get('name', '?')}: 第{fs.get('planted_chapter', '?')}章埋下"
            )
        if len(foreshadows) > 5:
            context_parts.append(f"- ...还有 {len(foreshadows) - 5} 个")
        context_parts.append("")

    if context_parts:
        return "\n".join(context_parts)
    return None


# =============================================================================
# Post-Tool Hooks
# =============================================================================


def _post_chapter_complete_hook(chapter: int, result: str) -> str:
    """Hook that runs after completing a chapter.

    Adds reminders about:
    - Checking for foreshadow resolution opportunities
    - Updating character statuses
    - Creating checkpoint if needed
    - Next chapter preparation

    Args:
        chapter: The completed chapter number
        result: The original tool result

    Returns:
        Enhanced result with reminders
    """
    db = _get_db()
    reminders = []

    # 1. Check for foreshadows that should have been resolved
    if db:
        foreshadows = db.list_foreshadows(include_resolved=False)
        due_foreshadows = [
            f for f in foreshadows if f.get("target_chapter") and f["target_chapter"] <= chapter
        ]
        if due_foreshadows:
            reminders.append("⚠️ 【伏笔提醒】以下伏笔已到预计回收章节：")
            for fs in due_foreshadows:
                reminders.append(f"   - {fs.get('name', '?')} (预计第{fs.get('target_chapter')}章)")
            reminders.append("   请检查是否已回收，使用 resolve_foreshadow() 标记")

    # 2. Remind to update character statuses if any significant events
    reminders.append("")
    reminders.append("📝 【记录提醒】")
    reminders.append("   - 如有角色状态变化，使用 update_character() 更新")
    reminders.append("   - 如埋下新伏笔，使用 plant_foreshadow() 记录")

    # 3. Auto-checkpoint logic (2-action rule inspired)
    global _hook_state
    _hook_state["operation_count"] += 1

    if _hook_state["operation_count"] >= _hook_state["checkpoint_threshold"]:
        if db:
            checkpoint_id = db.create_checkpoint(f"自动检查点-第{chapter}章后")
            reminders.append("")
            reminders.append(f"💾 【自动检查点】已创建 (ID: {checkpoint_id})")
            _hook_state["operation_count"] = 0
            _hook_state["last_checkpoint"] = datetime.now().isoformat()

    # 4. Next chapter preparation hint
    reminders.append("")
    reminders.append(f"📖 【下一步】准备写第{chapter + 1}章前，建议：")
    reminders.append("   - get_progress() 确认进度")
    reminders.append("   - list_foreshadows() 检查待回收伏笔")
    reminders.append("   - list_characters() 确认角色状态")

    return result + "\n\n" + "\n".join(reminders)


def _post_outline_complete_hook(chapter: int, result: str) -> str:
    """Hook that runs after completing an outline.

    Args:
        chapter: The completed outline chapter number
        result: The original tool result

    Returns:
        Enhanced result with reminders
    """
    reminders = []

    # Increment operation count
    global _hook_state
    _hook_state["operation_count"] += 1

    # Remind about outline continuation or writing
    reminders.append("")
    reminders.append("📝 【下一步选择】")
    reminders.append(f"   A. 继续写第{chapter + 1}章大纲")
    reminders.append(f"   B. 开始写第{chapter}章正文 (使用 complete_chapter)")

    return result + "\n\n" + "\n".join(reminders)


# =============================================================================
# Session Recovery Hook (5-Question Reboot Check inspired)
# =============================================================================


def get_session_recovery_context() -> str | None:
    """Generate session recovery context for interrupted sessions.

    Implements the "5-Question Reboot Check" from planning-with-files:
    1. Where am I in the codebase? → Current chapter/outline progress
    2. What was I doing? → Last operation from logs
    3. What have I discovered? → Recent memory entries
    4. What's left to do? → Pending foreshadows, next chapter
    5. What problems emerged? → Any failed operations

    Returns:
        Recovery context string or None if not needed
    """
    db = _get_db()
    project = _get_project()

    if db is None or project is None:
        return None

    context_parts = ["【会话恢复上下文】(5问检查)\n"]

    # 1. Where am I? - Current progress
    progress = db.get_progress()
    context_parts.append("1️⃣ 当前位置:")
    context_parts.append(
        f"   - 大纲进度: {progress.get('outline_completed', 0)}/{progress.get('outline_total', '?')}章"
    )
    context_parts.append(
        f"   - 正文进度: {progress.get('writing_completed', 0)}/{progress.get('writing_total', '?')}章"
    )
    context_parts.append(f"   - 当前章节: 第{progress.get('current_chapter', 1)}章")
    context_parts.append("")

    # 2. What was I doing? - Last operations
    pending_ops = db.get_pending_operations()
    if pending_ops:
        context_parts.append("2️⃣ 上次操作 (可能未完成):")
        for op in pending_ops[:3]:
            context_parts.append(f"   - {op.get('operation', '?')}: {op.get('status', '?')}")
            if op.get("error"):
                context_parts.append(f"     错误: {op.get('error')}")
        context_parts.append("")
    else:
        context_parts.append("2️⃣ 上次操作: 无未完成操作")
        context_parts.append("")

    # 3. What have I discovered? - Recent memory
    all_memory = db.recall()
    if all_memory:
        context_parts.append("3️⃣ 已记录的发现:")
        total_entries = sum(len(items) for items in all_memory.values())
        context_parts.append(f"   - 总记忆条目: {total_entries}条")
        for cat, items in list(all_memory.items())[:3]:
            context_parts.append(f"   - {cat}: {list(items.keys())[:3]}")
        context_parts.append("")

    # 4. What's left to do? - Pending items
    context_parts.append("4️⃣ 待完成事项:")
    foreshadows = db.list_foreshadows(include_resolved=False)
    if foreshadows:
        context_parts.append(f"   - 待回收伏笔: {len(foreshadows)}个")
        overdue = [
            f
            for f in foreshadows
            if f.get("target_chapter") and f["target_chapter"] <= progress.get("current_chapter", 1)
        ]
        if overdue:
            context_parts.append(f"   - 已超期伏笔: {len(overdue)}个 ⚠️")

    next_chapter = progress.get("current_chapter", 1)
    outline_completed = progress.get("outline_completed", 0)
    if next_chapter > outline_completed:
        context_parts.append(f"   - 需要先完成第{next_chapter}章大纲")
    else:
        context_parts.append(f"   - 可以开始写第{next_chapter}章正文")
    context_parts.append("")

    # 5. What problems emerged? - Check for issues
    context_parts.append("5️⃣ 问题检查:")
    issues = []

    # Check for stale characters
    characters = db.list_characters()
    stale_chars = [
        c
        for c in characters
        if progress.get("current_chapter", 1) - c.get("last_appearance", 0) > 10
    ]
    if stale_chars:
        issues.append(f"   - {len(stale_chars)}个角色超过10章未更新")

    # Check for orphaned foreshadows
    very_old_fs = [
        f
        for f in foreshadows
        if progress.get("current_chapter", 1) - f.get("planted_chapter", 0) > 20
    ]
    if very_old_fs:
        issues.append(f"   - {len(very_old_fs)}个伏笔埋下超过20章未回收")

    if issues:
        context_parts.extend(issues)
    else:
        context_parts.append("   - 无明显问题")

    return "\n".join(context_parts)


# =============================================================================
# Hook Decorators for Tool Wrapping
# =============================================================================


def with_pre_hook(hook_fn: Callable[..., str | None]) -> Callable[[F], F]:
    """Decorator to add a pre-execution hook to a tool.

    The hook function receives the same arguments as the decorated function.
    If it returns a string, that context is logged/available.

    Args:
        hook_fn: Function that returns context string or None
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute pre-hook
            try:
                context = hook_fn(*args, **kwargs)
                if context:
                    # Store context for potential use
                    _hook_state["last_pre_context"] = context
            except Exception:
                pass  # Hooks should not break the main flow

            # Execute original function
            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def with_post_hook(hook_fn: Callable[..., str]) -> Callable[[F], F]:
    """Decorator to add a post-execution hook to a tool.

    The hook function receives the original result and returns enhanced result.

    Args:
        hook_fn: Function that enhances the result
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute original function
            result = func(*args, **kwargs)

            # Execute post-hook
            try:
                enhanced_result = hook_fn(*args, result=result, **kwargs)
                return enhanced_result
            except Exception:
                return result  # Return original on hook failure

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# Hook Registration and Management
# =============================================================================


class NovelHooksRegistry:
    """Registry for managing novel writing hooks.

    Provides centralized management of all hooks and their configuration.
    """

    def __init__(self, project_path: Path):
        """Initialize the hooks registry.

        Args:
            project_path: Path to the novel project
        """
        self.project_path = project_path
        self.enabled_hooks: set[str] = {
            "pre_write_chapter",
            "pre_outline",
            "post_chapter_complete",
            "post_outline_complete",
            "session_recovery",
            "auto_checkpoint",
        }
        init_hooks(project_path)

    def enable_hook(self, hook_name: str) -> None:
        """Enable a specific hook."""
        self.enabled_hooks.add(hook_name)

    def disable_hook(self, hook_name: str) -> None:
        """Disable a specific hook."""
        self.enabled_hooks.discard(hook_name)

    def is_enabled(self, hook_name: str) -> bool:
        """Check if a hook is enabled."""
        return hook_name in self.enabled_hooks

    def get_pre_chapter_context(self, chapter: int) -> str | None:
        """Get pre-chapter writing context."""
        if not self.is_enabled("pre_write_chapter"):
            return None
        return _pre_write_chapter_hook(chapter)

    def get_pre_outline_context(self, chapter: int) -> str | None:
        """Get pre-outline writing context."""
        if not self.is_enabled("pre_outline"):
            return None
        return _pre_outline_hook(chapter)

    def enhance_chapter_result(self, chapter: int, result: str) -> str:
        """Enhance chapter completion result with post-hooks."""
        if not self.is_enabled("post_chapter_complete"):
            return result
        return _post_chapter_complete_hook(chapter, result)

    def enhance_outline_result(self, chapter: int, result: str) -> str:
        """Enhance outline completion result with post-hooks."""
        if not self.is_enabled("post_outline_complete"):
            return result
        return _post_outline_complete_hook(chapter, result)

    def get_recovery_context(self) -> str | None:
        """Get session recovery context."""
        if not self.is_enabled("session_recovery"):
            return None
        return get_session_recovery_context()

    def should_create_checkpoint(self) -> bool:
        """Check if auto-checkpoint should be created."""
        if not self.is_enabled("auto_checkpoint"):
            return False
        return _hook_state["operation_count"] >= _hook_state["checkpoint_threshold"]

    def reset_checkpoint_counter(self) -> None:
        """Reset the checkpoint operation counter."""
        _hook_state["operation_count"] = 0

    def get_status(self) -> dict[str, Any]:
        """Get current hooks status."""
        return {
            "enabled_hooks": list(self.enabled_hooks),
            "operation_count": _hook_state["operation_count"],
            "checkpoint_threshold": _hook_state["checkpoint_threshold"],
            "last_checkpoint": _hook_state["last_checkpoint"],
            "session_start": _hook_state["session_start"],
        }


# =============================================================================
# Middleware Integration Helper
# =============================================================================


def build_hooks_system_prompt_section(registry: NovelHooksRegistry) -> str:
    """Build the hooks-related section for system prompt injection.

    This provides the agent with awareness of the hooks system.

    Args:
        registry: The hooks registry

    Returns:
        System prompt section describing hooks behavior
    """
    lines = [
        "",
        "【Hooks系统 - 自动触发】",
        "",
        "本项目启用了自动Hooks系统，以下行为会自动触发：",
        "",
    ]

    if registry.is_enabled("pre_write_chapter"):
        lines.append("📖 写章节前: 自动加载上章摘要、章节大纲、活跃角色、临近伏笔")

    if registry.is_enabled("pre_outline"):
        lines.append("📝 写大纲前: 自动加载故事框架、前章大纲、角色状态、待回收伏笔")

    if registry.is_enabled("post_chapter_complete"):
        lines.append("✅ 章节完成后: 自动提醒检查伏笔、更新角色状态")

    if registry.is_enabled("auto_checkpoint"):
        lines.append(f"💾 自动检查点: 每{_hook_state['checkpoint_threshold']}次重要操作后自动保存")

    if registry.is_enabled("session_recovery"):
        lines.append("🔄 会话恢复: 新会话开始时自动提供5问恢复上下文")

    lines.append("")
    lines.append("你无需手动触发这些功能，系统会自动处理。")

    return "\n".join(lines)


__all__ = [
    "init_hooks",
    "get_session_recovery_context",
    "NovelHooksRegistry",
    "build_hooks_system_prompt_section",
    "with_pre_hook",
    "with_post_hook",
]
