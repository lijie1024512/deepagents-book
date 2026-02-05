"""CLI commands for novel writing.

Commands:
- deepagents novel init <title> [--world onepiece|naruto|original]
- deepagents novel list
- deepagents novel status [project]
- deepagents novel start [project] [--mode outline|write|revise]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from deepagents_cli.config import COLORS, Settings, console
from deepagents_cli.novel.project import NovelProject, list_projects


def _init(title: str, world: str | None, path: Path | None = None) -> None:
    """Initialize a new novel project.

    Args:
        title: Project title
        world: World type (onepiece/naruto/bleach/original), None means ask in conversation
        path: Optional custom path, defaults to ~/novels/<title>
    """
    if path is None:
        novels_dir = Path.home() / "novels"
        novels_dir.mkdir(parents=True, exist_ok=True)
        path = novels_dir / title

    if path.exists() and any(path.iterdir()):
        console.print(f"[bold red]错误:[/bold red] 目录已存在且不为空: {path}")
        return

    # 如果未指定世界观，设为 "unset"，在对话中询问
    actual_world = world if world else "unset"

    try:
        project = NovelProject.create(path, title, actual_world)
        console.print(f"\n[bold green]✓ 小说项目创建成功！[/bold green]")
        console.print(f"\n[bold]项目信息:[/bold]", style=COLORS["primary"])
        console.print(f"  标题: {title}")
        if world:
            console.print(f"  世界观: {world}")
        else:
            console.print(f"  世界观: [dim]未指定（启动创作时会询问）[/dim]")
        console.print(f"  位置: {path}")

        console.print(f"\n[bold]项目结构:[/bold]", style=COLORS["primary"])
        console.print(f"  {path}/")
        console.print(f"  ├── .novel/          # 项目配置和状态")
        console.print(f"  ├── world/           # 世界观设定")
        console.print(f"  ├── outline/         # 大纲")
        console.print(f"  ├── chapters/        # 正文章节")
        console.print(f"  └── output/          # 导出文件")

        console.print(f"\n[bold]下一步:[/bold]", style=COLORS["primary"])
        console.print(f"  1. 进入项目目录:")
        console.print(f"     cd {path}", style=COLORS["dim"])
        console.print(f"  2. 开始创作:")
        console.print(f"     deepagents novel start", style=COLORS["dim"])
        console.print(f"  或直接进入大纲模式:")
        console.print(f"     deepagents novel start --mode outline", style=COLORS["dim"])

    except Exception as e:
        console.print(f"[bold red]错误:[/bold red] 创建项目失败: {e}")


def _list() -> None:
    """List all novel projects."""
    projects = list_projects()

    if not projects:
        console.print("[yellow]没有找到小说项目。[/yellow]")
        console.print(f"\n[dim]创建你的第一个项目:[/dim]", style=COLORS["dim"])
        console.print(f"  deepagents novel init 我的小说 --world original", style=COLORS["dim"])
        return

    console.print(f"\n[bold]小说项目列表:[/bold]\n", style=COLORS["primary"])

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

    console.print(f"\n[bold]📊 进度:[/bold]", style=COLORS["primary"])
    console.print(f"   大纲: {state.outline_completed}/{state.outline_total or '未设定'} 章")
    console.print(f"   正文: {state.writing_completed}/{state.writing_total or '未设定'} 章")
    console.print(f"   当前: 第 {state.current_chapter} 章")

    # Character status
    if state.characters:
        console.print(f"\n[bold]👥 角色状态:[/bold]", style=COLORS["primary"])
        for name, char in state.characters.items():
            status_emoji = {"已收服": "✅", "敌对": "⚔️", "中立": "➖", "未出场": "❓"}.get(char.status, "❓")
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
        console.print(f"\n[bold]⚡ 进行中的冲突:[/bold]", style=COLORS["primary"])
        for conflict in state.active_conflicts[:3]:
            console.print(f"   - {conflict}", style=COLORS["dim"])

    console.print(f"\n[bold]🚀 继续创作:[/bold]", style=COLORS["primary"])
    console.print(f"   deepagents novel start", style=COLORS["dim"])


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

    console.print(f"\n[bold]🚀 启动小说创作会话[/bold]", style=COLORS["primary"])
    console.print(f"   项目: {config.title}")
    console.print(f"   世界观: {config.world_type}")
    console.print(f"   当前进度: 大纲 {state.outline_completed}/{state.outline_total or '?'} 章, "
                  f"正文 {state.writing_completed}/{state.writing_total or '?'} 章")
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

    This prompt provides context and asks the agent to guide the conversation.
    """
    config = project.config
    state = project.state

    # Include project context
    context = _build_project_context(project)

    if state.writing_completed == 0 and state.outline_completed == 0:
        # New project - need to setup everything
        if config.world_type == "unset":
            # 世界观未指定，先询问
            return f"""{context}

这是一个新项目，我想创作一部小说《{config.title}》。

首先，请问你想写什么类型的同人小说？

A. 海贼王同人（东海、伟大航路、四皇、海军）
B. 火影同人（木叶、晓组织、忍界大战）
C. 死神同人（尸魂界、虚圈、灭却师）
D. 原创小说（自建世界观）

请告诉我你的选择。"""
        else:
            return f"""{context}

这是一个新项目，我想创作一部小说《{config.title}》，世界观是{config.world_type}。

请帮我开始规划这部小说，通过对话引导我完成：
1. 主角设定
2. 故事框架
3. 第一卷大纲

用选择题的方式引导我，不要问开放性问题。"""

    elif state.outline_completed == 0:
        # Has title but no outline
        return f"""{context}

项目已创建但还没有大纲。请帮我规划大纲，通过对话引导我确定：
1. 主角核心设定
2. 第一卷的故事线
3. 前10章的详细大纲

用选择题的方式引导我。"""

    elif state.writing_completed < state.outline_completed:
        # Has outline, need to write
        return f"""{context}

大纲已有 {state.outline_completed} 章，正文写到了第 {state.writing_completed} 章。

请帮我继续写第 {state.current_chapter} 章的正文。先展示这章的场景规划，等我确认后再逐场景生成。"""

    else:
        # Caught up - ask what to do next
        return f"""{context}

当前大纲和正文进度相当。接下来你想做什么？

A. 续写大纲（规划后续章节的情节）
B. 继续写正文（把大纲展开成详细内容）
C. 优化已有内容（修改、润色、检查一致性）
D. 查看项目状态（角色、伏笔、剧情线）

请告诉我你的选择。"""


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
    state = project.state
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
    from deepagents_cli.sessions import generate_thread_id, get_checkpointer
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
                        assistant_id=f"novel-{project.config.title}",
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
                        assistant_id=f"novel-{project.config.title}",
                        backend=backend,
                        auto_approve=False,
                        cwd=project.path,
                        thread_id=thread_id,
                        initial_prompt=initial_prompt,
                    )
            except Exception as e:
                console.print(f"[bold red]错误:[/bold red] 创建会话失败: {e}")
                console.print(f"\n[dim]请确保已正确配置 API 密钥。[/dim]")
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
        f"【项目状态】",
        f"小说：《{config.title}》",
        f"世界观：{world_display}",
        f"",
        f"【创作进度】",
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
        context_parts.append(state.last_chapter_summary[:200] + "..." if len(state.last_chapter_summary) > 200 else state.last_chapter_summary)

    return "\n".join(context_parts)


def _resolve_project(project_name: str | None) -> NovelProject | None:
    """Resolve project from name or current directory.

    Args:
        project_name: Optional project name

    Returns:
        NovelProject instance or None if not found
    """
    if project_name:
        # Try to find by name in ~/novels
        novels_dir = Path.home() / "novels"
        project_path = novels_dir / project_name
        if project_path.exists():
            try:
                return NovelProject.load(project_path)
            except FileNotFoundError:
                pass

        console.print(f"[bold red]错误:[/bold red] 找不到项目: {project_name}")
        console.print(f"[dim]使用 'deepagents novel list' 查看所有项目[/dim]")
        return None

    # Try current directory
    project = NovelProject.find_project()
    if project:
        return project

    console.print("[bold red]错误:[/bold red] 当前目录不是小说项目")
    console.print(f"[dim]请指定项目名称或进入项目目录:[/dim]")
    console.print(f"  deepagents novel status <项目名>", style=COLORS["dim"])
    console.print(f"  cd ~/novels/<项目名> && deepagents novel status", style=COLORS["dim"])
    return None


def setup_novel_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Setup the novel subcommand parser."""
    novel_parser = subparsers.add_parser(
        "novel",
        help="小说创作工具",
        description="高性能小说生成Agent - 支持大纲生成、正文写作、修改优化",
    )
    novel_subparsers = novel_parser.add_subparsers(dest="novel_command", help="小说命令")

    # novel init
    init_parser = novel_subparsers.add_parser("init", help="初始化新的小说项目", description="创建一个新的小说项目")
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
    novel_subparsers.add_parser("list", help="列出所有小说项目", description="显示所有已创建的小说项目")

    # novel status
    status_parser = novel_subparsers.add_parser("status", help="查看项目状态", description="显示当前项目的详细状态")
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
    else:
        # No subcommand, show help
        console.print("[yellow]请指定一个子命令[/yellow]")
        console.print("\n[bold]用法:[/bold]", style=COLORS["primary"])
        console.print("  deepagents novel <command> [options]\n")
        console.print("[bold]可用命令:[/bold]", style=COLORS["primary"])
        console.print("  init <title>    创建新的小说项目")
        console.print("  list            列出所有项目")
        console.print("  status          查看项目状态")
        console.print("  start           开始创作会话")
        console.print("\n[bold]示例:[/bold]", style=COLORS["primary"])
        console.print("  deepagents novel init 我的小说 --world original")
        console.print("  deepagents novel list")
        console.print("  deepagents novel start --mode write")
        console.print("\n[dim]查看更多帮助:[/dim]", style=COLORS["dim"])
        console.print("  deepagents novel <command> --help", style=COLORS["dim"])


__all__ = ["setup_novel_parser", "execute_novel_command"]
