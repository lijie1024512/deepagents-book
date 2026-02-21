"""CLI commands for novel writing.

Commands:
- deepagents novel init <title> [--world onepiece|naruto|original]
- deepagents novel list
- deepagents novel status [project]
- deepagents novel start [project] [--mode outline|write|revise]
- deepagents novel checkpoint [name] - Create a named checkpoint
- deepagents novel checkpoint list - List all checkpoints
- deepagents novel checkpoint restore <id> - Restore a checkpoint
- deepagents novel migrate - Migrate old YAML projects to SQLite
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from deepagents_cli.config import COLORS, console
from deepagents_cli.novel.project import NovelProject, get_novels_base_dir, list_projects


def _init(title: str, world: str | None, path: Path | None = None) -> None:
    """Initialize a new novel project.

    Args:
        title: Project title
        world: World type (onepiece/naruto/bleach/original), None means ask in conversation
        path: Optional custom path, defaults to ./novels/<title>
    """
    if path is None:
        novels_dir = get_novels_base_dir()
        novels_dir.mkdir(parents=True, exist_ok=True)
        path = novels_dir / title

    if path.exists() and any(path.iterdir()):
        console.print(f"[bold red]错误:[/bold red] 目录已存在且不为空: {path}")
        return

    # 如果未指定世界观，设为 "unset"，在对话中询问
    actual_world = world if world else "unset"

    try:
        NovelProject.create(path, title, actual_world)
        console.print("\n[bold green]✓ 小说项目创建成功！[/bold green]")
        console.print("\n[bold]项目信息:[/bold]", style=COLORS["primary"])
        console.print(f"  标题: {title}")
        if world:
            console.print(f"  世界观: {world}")
        else:
            console.print("  世界观: [dim]未指定（启动创作时会询问）[/dim]")
        console.print(f"  位置: {path}")

        console.print("\n[bold]项目结构:[/bold]", style=COLORS["primary"])
        console.print(f"  {path}/")
        console.print("  ├── .novel/          # 项目配置和状态")
        console.print("  ├── world/           # 世界观设定")
        console.print("  ├── outline/         # 大纲")
        console.print("  ├── chapters/        # 正文章节")
        console.print("  └── output/          # 导出文件")

        console.print("\n[bold]下一步:[/bold]", style=COLORS["primary"])
        console.print("  开始创作:")
        console.print(f'     uv run deepagents novel start "{title}"', style=COLORS["dim"])
        console.print("  或直接进入大纲模式:")
        console.print(
            f'     uv run deepagents novel start "{title}" --mode outline', style=COLORS["dim"]
        )

    except Exception as e:
        console.print(f"[bold red]错误:[/bold red] 创建项目失败: {e}")


def _list() -> None:
    """List all novel projects."""
    projects = list_projects()

    if not projects:
        console.print("[yellow]没有找到小说项目。[/yellow]")
        console.print("\n[dim]创建你的第一个项目:[/dim]", style=COLORS["dim"])
        console.print(
            "  uv run deepagents novel init 我的小说 --world original", style=COLORS["dim"]
        )
        return

    console.print("\n[bold]小说项目列表:[/bold]\n", style=COLORS["primary"])

    for project in projects:
        config = project.config
        state = project.state

        # Status indicator
        if state.writing_completed > 0:
            status_icon = "📖"  # Writing in progress
        elif state.outline_completed > 0:
            status_icon = "📝"  # Outline done
        else:
            status_icon = "🆕"  # New project

        console.print(f"  {status_icon} [bold]{config.title}[/bold]", style=COLORS["primary"])
        console.print(f"     世界观: {config.world_type}", style=COLORS["dim"])
        console.print(
            f"     进度: 大纲 {state.outline_completed}/{state.outline_total or '?'} 章, "
            f"正文 {state.writing_completed}/{state.writing_total or '?'} 章",
            style=COLORS["dim"],
        )
        console.print(f"     位置: {project.path}", style=COLORS["dim"])
        console.print()


def _status(project_name: str | None = None) -> None:
    """Show project status.

    Args:
        project_name: Optional project name, uses current directory if not provided
    """
    project = _resolve_project(project_name)
    if project is None:
        return

    config = project.config
    state = project.state

    console.print(f"\n[bold]📚 {config.title}[/bold]", style=COLORS["primary"])
    console.print(f"   世界观: {config.world_type}")
    console.print(f"   位置: {project.path}")

    console.print("\n[bold]📊 进度:[/bold]", style=COLORS["primary"])
    console.print(f"   大纲: {state.outline_completed}/{state.outline_total or '未设定'} 章")
    console.print(f"   正文: {state.writing_completed}/{state.writing_total or '未设定'} 章")
    console.print(f"   当前: 第 {state.current_chapter} 章")

    # Character status
    if state.characters:
        console.print("\n[bold]👥 角色状态:[/bold]", style=COLORS["primary"])
        for name, char in state.characters.items():
            status_emoji = {"已收服": "✅", "敌对": "⚔️", "中立": "➖", "未出场": "❓"}.get(
                char.status, "❓"
            )
            console.print(f"   {status_emoji} {name}: {char.status}，位置: {char.location}")

    # Pending foreshadowing
    pending = [f for f in state.foreshadowing if not f.get("resolved", False)]
    if pending:
        console.print(f"\n[bold]📌 待回收伏笔 ({len(pending)}):[/bold]", style=COLORS["primary"])
        for f in pending[:5]:  # Show first 5
            console.print(f"   - 第{f['chapter']}章: {f['content'][:30]}...", style=COLORS["dim"])
        if len(pending) > 5:
            console.print(f"   ... 还有 {len(pending) - 5} 个", style=COLORS["dim"])

    # Active conflicts
    if state.active_conflicts:
        console.print("\n[bold]⚡ 进行中的冲突:[/bold]", style=COLORS["primary"])
        for conflict in state.active_conflicts[:3]:
            console.print(f"   - {conflict}", style=COLORS["dim"])

    console.print("\n[bold]🚀 继续创作:[/bold]", style=COLORS["primary"])
    console.print(f'   uv run deepagents novel start "{config.title}"', style=COLORS["dim"])


def _start(project_name: str | None = None, mode: str | None = None) -> None:
    """Start novel writing session in conversation mode.

    This launches an interactive conversation session with the novel-writer agent,
    using the Pure Skill pattern where all capabilities are injected via Skills
    and context is fully shared within a single agent.

    Args:
        project_name: Optional project name
        mode: Optional mode (outline/write/revise) - used to set initial prompt focus
    """
    project = _resolve_project(project_name)
    if project is None:
        return

    config = project.config
    state = project.state

    # Build initial prompt based on mode
    if mode == "outline":
        initial_prompt = _build_outline_prompt(project)
    elif mode == "write":
        initial_prompt = _build_write_prompt(project)
    elif mode == "revise":
        initial_prompt = _build_revise_prompt(project)
    else:
        initial_prompt = _build_default_prompt(project)

    console.print("\n[bold]🚀 启动小说创作会话[/bold]", style=COLORS["primary"])
    console.print(f"   项目: {config.title}")
    console.print(f"   世界观: {config.world_type}")
    console.print(
        f"   当前进度: 大纲 {state.outline_completed}/{state.outline_total or '?'} 章, "
        f"正文 {state.writing_completed}/{state.writing_total or '?'} 章"
    )
    console.print()

    # Set environment variables for the agent
    os.environ["NOVEL_PROJECT_PATH"] = str(project.path)
    os.environ["NOVEL_PROJECT_TITLE"] = config.title
    os.environ["NOVEL_WORLD_TYPE"] = config.world_type
    os.environ["NOVEL_CURRENT_CHAPTER"] = str(state.current_chapter)

    if mode:
        os.environ["NOVEL_MODE"] = mode

    # Launch the conversation session
    _launch_conversation_session(project, initial_prompt)


def _build_default_prompt(project: NovelProject) -> str:
    """Build default initial prompt for conversation mode.

    This prompt is phase-aware: it generates prompts based on current_phase
    from the database, guiding the agent to the right starting point.
    """
    from deepagents_cli.novel.memory_tools import PHASE_LABELS

    config = project.config
    state = project.state

    # Include project context
    context = _build_project_context(project)
    phase = state.current_phase
    phase_label = PHASE_LABELS.get(phase, phase)

    if phase == "brainstorm":
        if config.world_type == "unset":
            return f"""{context}

这是一个新项目，我想创作一部小说《{config.title}》。

当前阶段：{phase_label}
请按照阶段指导，帮我确定小说类型和核心吸引力。用选择题的方式引导我。"""
        else:
            return f"""{context}

这是一个新项目，我想创作一部小说《{config.title}》，世界观是{config.world_type}。

当前阶段：{phase_label}
请帮我确定故事的核心吸引力，并收集参考案例。用选择题的方式引导我。"""

    elif phase == "engine":
        return f"""{context}

当前阶段：{phase_label}
请为《{config.title}》设计创意引擎。生成至少3个"脑洞+引擎"方案供我选择。"""

    elif phase == "character":
        return f"""{context}

当前阶段：{phase_label}
请从已选定的引擎出发，帮我设计主角。包括基础设定、内在矛盾、致命弱点和角色弧光。"""

    elif phase == "outline":
        return f"""{context}

当前阶段：{phase_label}
大纲进度: {state.outline_completed}/{state.outline_total or "?"} 章。
请帮我规划弧线和章节大纲，5-10章一批。"""

    elif phase == "writing":
        return f"""{context}

当前阶段：{phase_label}
正文进度: {state.writing_completed}/{state.writing_total or "?"} 章，当前第 {state.current_chapter} 章。
请帮我继续写正文。先展示场景规划，等我确认后再逐场景生成。"""

    elif phase == "revision":
        return f"""{context}

当前阶段：{phase_label}
请对已完成的正文进行多维度诊断（结构、情感、角色、文笔），展示问题和修改方案。"""

    else:
        # Fallback
        return f"""{context}

当前阶段：{phase_label}
请继续帮我推进小说创作。"""


def _build_outline_prompt(project: NovelProject) -> str:
    """Build prompt for outline mode."""
    config = project.config
    state = project.state
    context = _build_project_context(project)

    if state.outline_completed == 0:
        if config.world_type == "unset":
            return f"""{context}

请帮我为《{config.title}》生成大纲。

首先，请问你想写什么类型的同人小说？

A. 海贼王同人（东海、伟大航路、四皇、海军）
B. 火影同人（木叶、晓组织、忍界大战）
C. 死神同人（尸魂界、虚圈、灭却师）
D. 原创小说（自建世界观）

请告诉我你的选择。"""
        else:
            return f"""{context}

请帮我为《{config.title}》生成大纲。世界观是{config.world_type}。

通过对话引导我完成：
1. 确定主角核心设定（性格、金手指、目标）
2. 设计第一卷的故事框架
3. 规划详细的章节大纲

用选择题的方式引导我，每次给我2-4个选项。"""
    else:
        return f"""{context}

请帮我续写《{config.title}》的大纲。当前已有 {state.outline_completed} 章大纲。

请先读取现有大纲，然后：
1. 分析可能的剧情走向
2. 生成2-3个分支供我选择
3. 我选择后再生成详细大纲

等我确认后再继续下一步。"""


def _build_write_prompt(project: NovelProject) -> str:
    """Build prompt for write mode."""
    config = project.config
    state = project.state
    context = _build_project_context(project)

    return f"""{context}

请帮我写《{config.title}》第 {state.current_chapter} 章的正文。

请先：
1. 读取这章的大纲（如果有的话）
2. 规划这章的场景划分
3. 展示场景规划给我确认

确认后再逐场景生成正文，每个场景生成后等我确认再继续。"""


def _build_revise_prompt(project: NovelProject) -> str:
    """Build prompt for revise mode."""
    config = project.config
    context = _build_project_context(project)

    return f"""{context}

我想修改优化《{config.title}》的内容。

你想修改哪个部分？

A. 大纲（调整情节、改变剧情走向）
B. 正文（优化描写、修改对话、调整节奏）
C. 角色设定（修改性格、能力、背景）
D. 世界观设定（调整规则、势力、地点）

请告诉我你的选择，以及具体想修改哪些章节或内容。"""


def _launch_conversation_session(project: NovelProject, initial_prompt: str):
    """Launch a conversation-driven novel writing session.

    This function creates a novel-specific agent and launches an interactive
    session using the existing TUI/Rich interface, following the Pure Skill
    pattern where context is fully shared.

    Args:
        project: The NovelProject instance
        initial_prompt: Initial prompt to send to the agent
    """
    import asyncio

    from deepagents_cli.agent import create_novel_agent
    from deepagents_cli.config import create_model, settings as cli_settings
    from deepagents_cli.sessions import get_checkpointer
    from deepagents_cli.tools import fetch_url, http_request, web_search

    console.print("[dim]正在启动对话式创作会话...[/dim]")
    console.print("[dim]输入 /help 查看帮助，Ctrl+C 退出[/dim]\n")

    async def run_session():
        # Generate thread_id based on project name for session persistence
        thread_id = f"novel-{project.config.title.replace(' ', '-').lower()}"

        # Create model
        model = create_model(None)  # Use default model

        async with get_checkpointer() as checkpointer:
            # Prepare tools
            tools = [http_request, fetch_url]
            if cli_settings.has_tavily:
                tools.append(web_search)

            try:
                # Create novel-specific agent
                agent, backend = create_novel_agent(
                    model=model,
                    project_path=project.path,
                    project_title=project.config.title,
                    world_type=project.config.world_type,
                    tools=tools,
                    auto_approve=False,
                    checkpointer=checkpointer,
                )

                # Determine UI mode based on platform
                if sys.platform == "win32":
                    # Windows: use terminal mode
                    from deepagents_cli.rich_adapter import run_rich_cli

                    await run_rich_cli(
                        agent=agent,
                        assistant_id=thread_id,
                        backend=backend,
                        auto_approve=False,
                        cwd=str(project.path),
                        thread_id=thread_id,
                        initial_prompt=initial_prompt,
                    )
                else:
                    # macOS/Linux: use TUI mode
                    from deepagents_cli.app import run_textual_app

                    await run_textual_app(
                        agent=agent,
                        assistant_id=thread_id,
                        backend=backend,
                        auto_approve=False,
                        cwd=project.path,
                        thread_id=thread_id,
                        initial_prompt=initial_prompt,
                    )
            except Exception as e:
                console.print(f"[bold red]错误:[/bold red] 创建会话失败: {e}")
                console.print("\n[dim]请确保已正确配置 API 密钥。[/dim]")
                return

    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]会话已结束[/yellow]")


def _build_project_context(project: NovelProject) -> str:
    """Build project context as part of the initial prompt.

    This provides the agent with current project state information
    to enable context-aware conversation.

    Args:
        project: The NovelProject instance

    Returns:
        Formatted project context string
    """
    config = project.config
    state = project.state

    world_display = config.world_type if config.world_type != "unset" else "未指定"
    context_parts = [
        "【项目状态】",
        f"小说：《{config.title}》",
        f"世界观：{world_display}",
        "",
        "【创作进度】",
        f"- 大纲：{state.outline_completed}/{state.outline_total or '?'} 章",
        f"- 正文：{state.writing_completed}/{state.writing_total or '?'} 章",
        f"- 当前：第 {state.current_chapter} 章",
    ]

    # Add character states
    if state.characters:
        context_parts.append("")
        context_parts.append("【角色状态】")
        for name, char in state.characters.items():
            context_parts.append(f"- {name}：{char.status}，位置：{char.location}")

    # Add pending foreshadowing
    pending = [f for f in state.foreshadowing if not f.get("resolved", False)]
    if pending:
        context_parts.append("")
        context_parts.append(f"【待回收伏笔】（{len(pending)} 个）")
        for f in pending[:5]:
            context_parts.append(f"- 第{f['chapter']}章：{f['content'][:30]}...")
        if len(pending) > 5:
            context_parts.append(f"- ...还有 {len(pending) - 5} 个")

    # Add last chapter summary
    if state.last_chapter_summary:
        context_parts.append("")
        context_parts.append("【上一章摘要】")
        context_parts.append(
            state.last_chapter_summary[:200] + "..."
            if len(state.last_chapter_summary) > 200
            else state.last_chapter_summary
        )

    return "\n".join(context_parts)


def _checkpoint(
    project_name: str | None = None, name: str | None = None, action: str = "create"
) -> None:
    """Manage project checkpoints.

    Args:
        project_name: Optional project name
        name: Checkpoint name (for create) or ID (for restore)
        action: Action to perform (create/list/restore)
    """
    project = _resolve_project(project_name)
    if project is None:
        return

    if not project.uses_sqlite:
        console.print("[yellow]提示：该项目使用旧版存储格式，请先运行迁移命令。[/yellow]")
        console.print("  uv run deepagents novel migrate", style=COLORS["dim"])
        return

    if action == "list":
        checkpoints = project.list_checkpoints()
        if not checkpoints:
            console.print("[yellow]暂无检查点。[/yellow]")
            console.print("\n[dim]创建检查点：[/dim]", style=COLORS["dim"])
            console.print("  uv run deepagents novel checkpoint [name]", style=COLORS["dim"])
            return

        console.print("\n[bold]📋 检查点列表[/bold]", style=COLORS["primary"])
        console.print()
        for cp in checkpoints:
            cp_type = "🔹 手动" if cp.get("checkpoint_type") == "manual" else "🔸 自动"
            cp_name = cp.get("name") or "(无名称)"
            console.print(f"  {cp_type} ID: {cp['id']} - {cp_name}")
            console.print(f"       创建于: {cp.get('created_at', '未知')}", style=COLORS["dim"])
        console.print()
        console.print("[dim]恢复检查点：uv run deepagents novel checkpoint restore <id>[/dim]")

    elif action == "restore":
        if not name:
            console.print("[bold red]错误:[/bold red] 请指定要恢复的检查点 ID")
            return

        try:
            checkpoint_id = int(name)
        except ValueError:
            console.print(f"[bold red]错误:[/bold red] 检查点 ID 必须是数字: {name}")
            return

        success = project.restore_checkpoint(checkpoint_id)
        if success:
            console.print(f"[bold green]✓ 已恢复到检查点 {checkpoint_id}[/bold green]")
            # Show current state after restore
            _status(project_name)
        else:
            console.print(
                f"[bold red]错误:[/bold red] 恢复检查点失败，ID {checkpoint_id} 可能不存在"
            )

    else:  # create
        checkpoint_id = project.create_named_checkpoint(name)
        if name:
            console.print(f"[bold green]✓ 检查点已创建: {name} (ID: {checkpoint_id})[/bold green]")
        else:
            console.print(f"[bold green]✓ 检查点已创建 (ID: {checkpoint_id})[/bold green]")


def _migrate(
    project_name: str | None = None, remove_backups: bool = False, rollback: bool = False
) -> None:
    """Migrate project from YAML/JSON to SQLite.

    Args:
        project_name: Optional project name
        remove_backups: If True, remove backup files after migration
        rollback: If True, rollback migration and restore old files
    """
    from deepagents_cli.novel.migrate import (
        cleanup_old_files,
        get_migration_status,
        migrate_project,
        rollback_migration,
    )

    project = _resolve_project(project_name)
    if project is None:
        return

    # Get migration status
    status = get_migration_status(project.path)

    if rollback:
        if not status["has_backups"]:
            console.print("[bold red]错误:[/bold red] 没有备份文件可用于回滚")
            return

        console.print("[yellow]正在回滚迁移...[/yellow]")
        result = rollback_migration(project.path)

        if result["success"]:
            console.print("[bold green]✓ 迁移已回滚[/bold green]")
            console.print(f"  已恢复: {', '.join(result['restored_files'])}")
        else:
            console.print("[bold red]回滚失败:[/bold red]")
            for error in result["errors"]:
                console.print(f"  - {error}")
        return

    if status["format"] == "sqlite" and not status["has_backups"]:
        console.print("[green]✓ 项目已使用 SQLite 存储格式，无需迁移。[/green]")
        return

    if status["format"] == "sqlite" and status["has_backups"]:
        if remove_backups:
            console.print("[yellow]正在清理备份文件...[/yellow]")
            removed = cleanup_old_files(project.path, remove_backups=True)
            if removed:
                console.print("[green]✓ 已删除备份文件:[/green]")
                for f in removed:
                    console.print(f"  - {f}", style=COLORS["dim"])
            else:
                console.print("[yellow]没有找到备份文件。[/yellow]")
        else:
            console.print("[green]✓ 项目已使用 SQLite 存储格式。[/green]")
            console.print("  [dim]备份文件仍然存在。使用 --remove-backups 删除。[/dim]")
        return

    if status["format"] == "empty":
        console.print("[yellow]项目没有任何状态数据需要迁移。[/yellow]")
        return

    # Perform migration
    console.print("[bold]正在迁移项目到 SQLite 存储格式...[/bold]")
    console.print()

    result = migrate_project(project.path, backup=True)

    if result["success"]:
        console.print("[bold green]✓ 迁移完成！[/bold green]")
        console.print()
        if result["migrated_files"]:
            console.print("[bold]已迁移:[/bold]")
            for f in result["migrated_files"]:
                console.print(f"  ✓ {f}")
        if result["backed_up_files"]:
            console.print()
            console.print("[bold]已备份:[/bold]")
            for f in result["backed_up_files"]:
                console.print(f"  📦 {f}", style=COLORS["dim"])
        console.print()
        console.print("[dim]如需回滚: uv run deepagents novel migrate --rollback[/dim]")
        console.print("[dim]删除备份: uv run deepagents novel migrate --remove-backups[/dim]")
    else:
        console.print("[bold red]迁移失败:[/bold red]")
        for error in result["errors"]:
            console.print(f"  - {error}")
        if result["migrated_files"]:
            console.print()
            console.print("[yellow]部分已迁移:[/yellow]")
            for f in result["migrated_files"]:
                console.print(f"  ⚠ {f}")


def _session(action: str, thread_id: str | None = None) -> None:
    """Manage novel/imitate conversation sessions (LangGraph checkpoints).

    Args:
        action: Action to perform (list/view/delete/reset).
        thread_id: Thread ID (for view/delete).
    """
    import asyncio

    from rich.table import Table

    from deepagents_cli.sessions import delete_thread, get_db_path, list_threads

    async def _list_sessions() -> list[dict]:
        """List all novel/imitate sessions."""
        all_threads = await list_threads(limit=100)
        # Filter to novel/imitate sessions only
        return [
            t
            for t in all_threads
            if t["thread_id"]
            and (t["thread_id"].startswith("novel-") or t["thread_id"].startswith("imitate-"))
        ]

    async def _get_session_detail(tid: str) -> dict | None:
        """Get detail info for a session."""
        import aiosqlite

        db_path = str(get_db_path())
        async with aiosqlite.connect(db_path, timeout=30.0) as conn:
            # Check if table exists
            query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkpoints'"
            async with conn.execute(query) as cursor:
                if await cursor.fetchone() is None:
                    return None

            # Get checkpoint count and timestamps
            query = """
                SELECT COUNT(*) as cp_count,
                       MIN(json_extract(metadata, '$.updated_at')) as first_at,
                       MAX(json_extract(metadata, '$.updated_at')) as last_at,
                       json_extract(metadata, '$.agent_name') as agent_name
                FROM checkpoints
                WHERE thread_id = ?
            """
            async with conn.execute(query, (tid,)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] == 0:
                    return None
                return {
                    "thread_id": tid,
                    "checkpoint_count": row[0],
                    "first_at": row[1],
                    "last_at": row[2],
                    "agent_name": row[3],
                }

    async def _delete_all_novel_sessions() -> int:
        """Delete all novel/imitate sessions. Returns count deleted."""
        sessions = await _list_sessions()
        count = 0
        for s in sessions:
            if await delete_thread(s["thread_id"]):
                count += 1
        return count

    if action == "list":
        sessions = asyncio.run(_list_sessions())
        if not sessions:
            console.print("[yellow]没有找到小说/仿写会话。[/yellow]")
            return

        table = Table(
            title="小说/仿写会话列表",
            show_header=True,
            header_style=f"bold {COLORS['primary']}",
        )
        table.add_column("Thread ID", style="bold")
        table.add_column("类型")
        table.add_column("最后更新", style="dim")

        for s in sessions:
            tid = s["thread_id"]
            session_type = "仿写" if tid.startswith("imitate-") else "原创"
            updated = s.get("updated_at") or ""
            table.add_row(tid, session_type, updated)

        console.print()
        console.print(table)
        console.print()
        console.print("[dim]查看详情: uv run deepagents novel session view <thread_id>[/dim]")
        console.print("[dim]删除会话: uv run deepagents novel session delete <thread_id>[/dim]")

    elif action == "view":
        if not thread_id:
            console.print("[bold red]错误:[/bold red] 请指定 thread_id")
            console.print("[dim]用法: uv run deepagents novel session view <thread_id>[/dim]")
            return

        detail = asyncio.run(_get_session_detail(thread_id))
        if not detail:
            console.print(f"[bold red]错误:[/bold red] 会话 '{thread_id}' 不存在")
            return

        tid = detail["thread_id"]
        session_type = "仿写" if tid.startswith("imitate-") else "原创"
        project_name_part = tid.split("-", 1)[1] if "-" in tid else tid

        console.print(f"\n[bold]会话详情[/bold]", style=COLORS["primary"])
        console.print(f"  Thread ID: {tid}")
        console.print(f"  类型: {session_type}")
        console.print(f"  项目: {project_name_part}")
        console.print(f"  Agent: {detail.get('agent_name') or '未知'}")
        console.print(f"  检查点数: {detail['checkpoint_count']}")
        console.print(f"  首次创建: {detail.get('first_at') or '未知'}")
        console.print(f"  最后更新: {detail.get('last_at') or '未知'}")
        console.print()

    elif action == "delete":
        if not thread_id:
            console.print("[bold red]错误:[/bold red] 请指定 thread_id")
            console.print("[dim]用法: uv run deepagents novel session delete <thread_id>[/dim]")
            return

        deleted = asyncio.run(delete_thread(thread_id))
        if deleted:
            console.print(f"[bold green]✓ 会话 '{thread_id}' 已删除[/bold green]")
        else:
            console.print(f"[bold red]错误:[/bold red] 会话 '{thread_id}' 不存在")

    elif action == "reset":
        count = asyncio.run(_delete_all_novel_sessions())
        if count > 0:
            console.print(f"[bold green]✓ 已删除 {count} 个小说/仿写会话[/bold green]")
        else:
            console.print("[yellow]没有找到需要删除的会话。[/yellow]")

    else:
        console.print(f"[bold red]错误:[/bold red] 未知操作: {action}")
        console.print("[dim]可用操作: list, view, delete, reset[/dim]")


def _resolve_project(project_name: str | None) -> NovelProject | None:
    """Resolve project from name or current directory.

    Args:
        project_name: Optional project name

    Returns:
        NovelProject instance or None if not found
    """
    if project_name:
        # Try to find by name in <repo-root>/novels
        novels_dir = get_novels_base_dir()
        project_path = novels_dir / project_name
        if project_path.exists():
            try:
                return NovelProject.load(project_path)
            except FileNotFoundError:
                pass

        console.print(f"[bold red]错误:[/bold red] 找不到项目: {project_name}")
        console.print("[dim]使用 'uv run deepagents novel list' 查看所有项目[/dim]")
        return None

    # Try current directory
    project = NovelProject.find_project()
    if project:
        return project

    console.print("[bold red]错误:[/bold red] 未找到小说项目")
    console.print("[dim]请指定项目名称:[/dim]")
    console.print("  uv run deepagents novel status <项目名>", style=COLORS["dim"])
    console.print("  uv run deepagents novel list  # 查看所有项目", style=COLORS["dim"])
    return None


def _imitate_init(
    title: str,
    source: Path,
    path: Path | None = None,
) -> None:
    """Initialize a new imitation project.

    Args:
        title: New novel title.
        source: Path to source novel file.
        path: Optional custom project path.
    """
    from deepagents_cli.novel.imitate_tools import setup_imitate_project

    # Validate source file
    source = source.resolve()
    if not source.exists():
        console.print(f"[bold red]错误:[/bold red] 源文件不存在: {source}")
        return
    if not source.is_file():
        console.print(f"[bold red]错误:[/bold red] 源路径不是文件: {source}")
        return

    file_size = source.stat().st_size
    if file_size == 0:
        console.print("[bold red]错误:[/bold red] 源文件为空")
        return
    if file_size > 20 * 1024 * 1024:  # 50MB limit
        console.print("[bold red]错误:[/bold red] 源文件过大（超过50MB）")
        console.print(f"[dim]当前文件大小: {file_size / 1024 / 1024:.1f}MB[/dim]")
        return

    # Determine project path
    if path is None:
        novels_dir = get_novels_base_dir()
        novels_dir.mkdir(parents=True, exist_ok=True)
        path = novels_dir / title

    if path.exists() and any(path.iterdir()):
        console.print(f"[bold red]错误:[/bold red] 目录已存在且不为空: {path}")
        return

    try:
        # Create project with NovelProject.create first (sets up .novel/ and db)
        project = NovelProject.create(path, title, "original")

        # Update config for imitate mode
        project._config.mode = "imitate"
        project._config.source_file = f"source/{source.name}"
        project.save_config()

        # Setup imitate-specific tables and copy source file
        setup_imitate_project(path, source, title)

        console.print("\n[bold green]✓ 仿写项目创建成功！[/bold green]")
        console.print("\n[bold]项目信息:[/bold]", style=COLORS["primary"])
        console.print(f"  标题: {title}")
        console.print(f"  源小说: {source.name} ({file_size / 1024:.1f}KB)")
        console.print(f"  位置: {path}")

        console.print("\n[bold]项目结构:[/bold]", style=COLORS["primary"])
        console.print(f"  {path}/")
        console.print("  ├── .novel/          # 项目配置和数据库")
        console.print("  ├── source/          # 源小说文件")
        console.print("  ├── analysis/        # 分析成果")
        console.print("  ├── chapters/        # 生成的新章节")
        console.print("  └── output/          # 导出文件")

        console.print("\n[bold]下一步:[/bold]", style=COLORS["primary"])
        console.print(f'  uv run deepagents novel imitate start "{title}"', style=COLORS["dim"])

    except Exception as e:
        console.print(f"[bold red]错误:[/bold red] 创建仿写项目失败: {e}")


def _imitate_start(project_name: str | None = None) -> None:
    """Start an imitation writing session.

    Args:
        project_name: Optional project name.
    """
    project = _resolve_project(project_name)
    if project is None:
        return

    config = project.config
    if config.mode != "imitate":
        console.print("[bold red]错误:[/bold red] 该项目不是仿写项目。请使用 'novel start' 命令。")
        return

    from deepagents_cli.novel.imitate_tools import init_imitate_store

    init_imitate_store(project.path)

    console.print("\n[bold]🚀 启动仿写会话[/bold]", style=COLORS["primary"])
    console.print(f"   项目: {config.title}")
    console.print(f"   源小说: {config.source_file}")
    console.print()

    initial_prompt = _build_imitate_prompt(project)

    # Set environment variables
    os.environ["NOVEL_PROJECT_PATH"] = str(project.path)
    os.environ["NOVEL_PROJECT_TITLE"] = config.title
    os.environ["NOVEL_MODE"] = "imitate"

    _launch_imitate_session(project, initial_prompt)


def _imitate_status(project_name: str | None = None) -> None:
    """Show imitation project status.

    Args:
        project_name: Optional project name.
    """
    project = _resolve_project(project_name)
    if project is None:
        return

    config = project.config
    if config.mode != "imitate":
        console.print("[bold red]错误:[/bold red] 该项目不是仿写项目。")
        return

    from deepagents_cli.novel.imitate_tools import _get_db, init_imitate_store

    init_imitate_store(project.path)
    db = _get_db()

    console.print(f"\n[bold]📚 仿写项目: {config.title}[/bold]", style=COLORS["primary"])
    console.print(f"   源小说: {config.source_file}")
    console.print(f"   位置: {project.path}")

    if db is not None:
        with db._connection() as conn:
            # Source info
            row = conn.execute(
                "SELECT total_chars, total_chapters FROM imitate_source WHERE id=1"
            ).fetchone()
            if row and row[0]:
                console.print(f"   总字数: {row[0]:,} 字")
                console.print(f"   总章数: {row[1]} 章")

            # Analysis keys
            analysis_keys = conn.execute("SELECT key FROM imitate_analysis ORDER BY key").fetchall()
            if analysis_keys:
                keys_str = ", ".join(k[0] for k in analysis_keys)
                console.print(f"\n[bold]已保存分析:[/bold]", style=COLORS["primary"])
                console.print(f"   {keys_str}")

            # Generated chapters
            chapters = conn.execute(
                "SELECT chapter, title FROM imitate_chapters ORDER BY chapter"
            ).fetchall()
            if chapters:
                console.print(
                    f"\n[bold]已生成章节:[/bold] {len(chapters)} 章", style=COLORS["primary"]
                )
                for ch_num, ch_title in chapters:
                    console.print(f"   第{ch_num}章: {ch_title or '(无标题)'}")


def _build_imitate_prompt(project: NovelProject) -> str:
    """Build initial prompt for imitation session.

    Checks existing project state to avoid redundant index rebuilding.

    Args:
        project: The novel project.

    Returns:
        Initial prompt string.
    """
    config = project.config

    # Check existing state to build a smarter prompt
    from deepagents_cli.novel.imitate_tools import _get_db

    db = _get_db()
    has_index = False
    has_analysis = False
    chapter_count = 0

    if db is not None:
        with db._connection() as conn:
            row = conn.execute("SELECT total_chapters FROM imitate_source WHERE id=1").fetchone()
            has_index = bool(row and row[0])
            analysis_count = conn.execute("SELECT COUNT(*) FROM imitate_analysis").fetchone()[0]
            has_analysis = analysis_count > 0
            chapter_count = conn.execute("SELECT COUNT(*) FROM imitate_chapters").fetchone()[0]

    if chapter_count > 0:
        return (
            f"我正在进行小说仿写项目《{config.title}》。\n\n"
            f"项目已有进度：已生成 {chapter_count} 章。\n"
            f"请用 get_project_status 查看当前状态，然后继续仿写工作。"
        )
    if has_analysis:
        return (
            f"我正在进行小说仿写项目《{config.title}》。\n\n"
            f"已完成DNA分析和改编计划。\n"
            f"请用 get_project_status 查看当前状态，准备开始逐章生成。"
        )
    if has_index:
        return (
            f"我正在进行小说仿写项目《{config.title}》。\n\n"
            f"源小说索引已建立。\n"
            f"请用 get_project_status 查看当前状态，然后根据我的需求进行仿写。"
        )
    return (
        f"我正在进行小说仿写项目《{config.title}》。\n\n"
        f"源小说文件位于 /source/ 目录。\n"
        f"请先用 index_source 建立目录索引，然后根据我的需求进行仿写。"
    )


def _launch_imitate_session(project: NovelProject, initial_prompt: str) -> None:
    """Launch an imitation writing conversation session.

    Args:
        project: The NovelProject instance.
        initial_prompt: Initial prompt to send to the agent.
    """
    import asyncio

    from deepagents_cli.agent import create_imitate_agent
    from deepagents_cli.config import create_model, settings as cli_settings
    from deepagents_cli.sessions import get_checkpointer
    from deepagents_cli.tools import fetch_url, http_request, web_search

    console.print("[dim]正在启动仿写会话...[/dim]")
    console.print("[dim]输入 /help 查看帮助，Ctrl+C 退出[/dim]\n")

    async def run_session():
        thread_id = f"imitate-{project.config.title.replace(' ', '-').lower()}"
        model = create_model(None)

        async with get_checkpointer() as checkpointer:
            tools = [http_request, fetch_url]
            if cli_settings.has_tavily:
                tools.append(web_search)

            try:
                agent, backend = create_imitate_agent(
                    model=model,
                    project_path=project.path,
                    project_title=project.config.title,
                    tools=tools,
                    auto_approve=False,
                    checkpointer=checkpointer,
                )

                if sys.platform == "win32":
                    from deepagents_cli.rich_adapter import run_rich_cli

                    await run_rich_cli(
                        agent=agent,
                        assistant_id=thread_id,
                        backend=backend,
                        auto_approve=False,
                        cwd=str(project.path),
                        thread_id=thread_id,
                        initial_prompt=initial_prompt,
                    )
                else:
                    from deepagents_cli.app import run_textual_app

                    await run_textual_app(
                        agent=agent,
                        assistant_id=thread_id,
                        backend=backend,
                        auto_approve=False,
                        cwd=project.path,
                        thread_id=thread_id,
                        initial_prompt=initial_prompt,
                    )
            except Exception as e:
                console.print(f"[bold red]错误:[/bold red] 创建仿写会话失败: {e}")
                console.print("\n[dim]请确保已正确配置 API 密钥。[/dim]")
                return

    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]仿写会话已结束[/yellow]")


def setup_novel_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Setup the novel subcommand parser."""
    novel_parser = subparsers.add_parser(
        "novel",
        help="小说创作工具",
        description="高性能小说生成Agent - 支持大纲生成、正文写作、修改优化",
    )
    novel_subparsers = novel_parser.add_subparsers(dest="novel_command", help="小说命令")

    # novel init
    init_parser = novel_subparsers.add_parser(
        "init", help="初始化新的小说项目", description="创建一个新的小说项目"
    )
    init_parser.add_argument("title", help="小说标题")
    init_parser.add_argument(
        "--world",
        "-w",
        choices=["onepiece", "naruto", "bleach", "original"],
        default=None,
        help="世界观类型（可选，不指定则在对话中询问）",
    )
    init_parser.add_argument("--path", "-p", type=Path, help="自定义项目路径")

    # novel list
    novel_subparsers.add_parser(
        "list", help="列出所有小说项目", description="显示所有已创建的小说项目"
    )

    # novel status
    status_parser = novel_subparsers.add_parser(
        "status", help="查看项目状态", description="显示当前项目的详细状态"
    )
    status_parser.add_argument("project", nargs="?", help="项目名称（可选，默认使用当前目录）")

    # novel start
    start_parser = novel_subparsers.add_parser(
        "start", help="开始创作会话", description="启动交互式创作会话"
    )
    start_parser.add_argument("project", nargs="?", help="项目名称（可选，默认使用当前目录）")
    start_parser.add_argument(
        "--mode",
        "-m",
        choices=["outline", "write", "revise"],
        help="创作模式: outline(大纲), write(正文), revise(修改)",
    )

    # novel checkpoint
    checkpoint_parser = novel_subparsers.add_parser(
        "checkpoint", help="管理检查点", description="创建、查看、恢复项目检查点"
    )
    checkpoint_parser.add_argument(
        "action",
        nargs="?",
        default="create",
        help="操作: create(创建)/list(列表)/restore(恢复)，或检查点名称",
    )
    checkpoint_parser.add_argument(
        "name",
        nargs="?",
        help="检查点名称（创建时）或ID（恢复时）",
    )
    checkpoint_parser.add_argument("--project", "-p", help="项目名称（可选）")

    # novel migrate
    migrate_parser = novel_subparsers.add_parser(
        "migrate", help="迁移到SQLite", description="将旧版YAML/JSON项目迁移到SQLite存储格式"
    )
    migrate_parser.add_argument("project", nargs="?", help="项目名称（可选，默认使用当前目录）")
    migrate_parser.add_argument(
        "--remove-backups",
        action="store_true",
        help="删除备份文件（仅在已迁移后）",
    )
    migrate_parser.add_argument(
        "--rollback",
        action="store_true",
        help="回滚迁移，恢复原始文件",
    )

    # novel session
    session_parser = novel_subparsers.add_parser(
        "session", help="管理会话", description="查看、删除、重置小说/仿写的对话会话"
    )
    session_parser.add_argument(
        "action",
        choices=["list", "view", "delete", "reset"],
        help="操作: list(列表)/view(查看)/delete(删除)/reset(重置全部)",
    )
    session_parser.add_argument(
        "thread_id",
        nargs="?",
        help="会话 Thread ID（view/delete 时必填）",
    )

    # novel imitate
    imitate_parser = novel_subparsers.add_parser(
        "imitate", help="仿写工具", description="基于源小说进行仿写创作"
    )
    imitate_subs = imitate_parser.add_subparsers(dest="imitate_command", help="仿写命令")

    # novel imitate init <title> --source <file>
    imitate_init = imitate_subs.add_parser("init", help="初始化仿写项目")
    imitate_init.add_argument("title", help="新小说标题")
    imitate_init.add_argument("--source", "-s", required=True, type=Path, help="源小说文件路径")
    imitate_init.add_argument("--path", "-p", type=Path, help="自定义项目路径")

    # novel imitate start [project]
    imitate_start = imitate_subs.add_parser("start", help="开始仿写会话")
    imitate_start.add_argument("project", nargs="?", help="项目名称")

    # novel imitate status [project]
    imitate_status = imitate_subs.add_parser("status", help="查看仿写状态")
    imitate_status.add_argument("project", nargs="?", help="项目名称")

    return novel_parser


def execute_novel_command(args: argparse.Namespace) -> None:
    """Execute novel subcommands based on parsed arguments."""
    if args.novel_command == "init":
        _init(args.title, args.world, args.path)
    elif args.novel_command == "list":
        _list()
    elif args.novel_command == "status":
        _status(getattr(args, "project", None))
    elif args.novel_command == "start":
        _start(getattr(args, "project", None), getattr(args, "mode", None))
    elif args.novel_command == "checkpoint":
        action = getattr(args, "action", "create")
        name = getattr(args, "name", None)
        project = getattr(args, "project", None)

        # Handle "checkpoint list" and "checkpoint restore <id>"
        if action == "list":
            _checkpoint(project, None, action="list")
        elif action == "restore":
            _checkpoint(project, name, action="restore")
        else:
            # "checkpoint" or "checkpoint <name>" - create mode
            # If action is not a known action, treat it as the checkpoint name
            if action not in ("create", "list", "restore"):
                name = action
            _checkpoint(project, name, action="create")
    elif args.novel_command == "migrate":
        _migrate(
            getattr(args, "project", None),
            getattr(args, "remove_backups", False),
            getattr(args, "rollback", False),
        )
    elif args.novel_command == "session":
        _session(
            action=args.action,
            thread_id=getattr(args, "thread_id", None),
        )
    elif args.novel_command == "imitate":
        imitate_cmd = getattr(args, "imitate_command", None)
        if imitate_cmd == "init":
            _imitate_init(
                args.title,
                args.source,
                getattr(args, "path", None),
            )
        elif imitate_cmd == "start":
            _imitate_start(getattr(args, "project", None))
        elif imitate_cmd == "status":
            _imitate_status(getattr(args, "project", None))
        else:
            console.print("[yellow]请指定仿写子命令[/yellow]")
            console.print("\n[bold]用法:[/bold]", style=COLORS["primary"])
            console.print("  uv run deepagents novel imitate init <标题> --source <文件>")
            console.print("  uv run deepagents novel imitate start [项目名]")
            console.print("  uv run deepagents novel imitate status [项目名]")
    else:
        # No subcommand, show help
        console.print("[yellow]请指定一个子命令[/yellow]")
        console.print("\n[bold]用法:[/bold]", style=COLORS["primary"])
        console.print("  uv run deepagents novel <command> [options]\n")
        console.print("[bold]可用命令:[/bold]", style=COLORS["primary"])
        console.print("  init <title>    创建新的小说项目")
        console.print("  list            列出所有项目")
        console.print("  status <项目名>  查看项目状态")
        console.print("  start <项目名>   开始创作会话")
        console.print("  checkpoint      管理检查点")
        console.print("  session         管理对话会话（增删改查）")
        console.print("  migrate         迁移到SQLite存储")
        console.print("  imitate         仿写工具")
        console.print("\n[bold]示例:[/bold]", style=COLORS["primary"])
        console.print("  uv run deepagents novel init 我的小说 --world original")
        console.print("  uv run deepagents novel list")
        console.print("  uv run deepagents novel start 我的小说")
        console.print("  uv run deepagents novel start 我的小说 --mode outline")
        console.print("  uv run deepagents novel imitate init 新作 --source 源小说.txt")
        console.print("  uv run deepagents novel session list")
        console.print("  uv run deepagents novel session delete <thread_id>")
        console.print("  uv run deepagents novel session reset")
        console.print("\n[dim]注意：请在 libs/deepagents-cli/ 目录下运行以上命令[/dim]")


__all__ = ["setup_novel_parser", "execute_novel_command"]
