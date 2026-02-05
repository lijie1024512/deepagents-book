"""Agent management and creation for the CLI."""

import os
import shutil
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.sandbox import SandboxBackendProtocol
from deepagents.middleware import MemoryMiddleware, SkillsMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware import (
    InterruptOnConfig,
)
from langchain.agents.middleware.types import AgentState
from langchain.messages import ToolCall
from langchain.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.pregel import Pregel
from langgraph.runtime import Runtime

from deepagents_cli.config import COLORS, config, console, extract_builtin_skills, get_default_coding_instructions, settings
from deepagents_cli.integrations.sandbox_factory import get_default_working_dir
from deepagents_cli.local_context import LocalContextMiddleware
from deepagents_cli.novel_prompt import NovelPromptMiddleware
from deepagents_cli.prompt_optimizer_middleware import PromptOptimizerMiddleware
from deepagents_cli.shell import ShellMiddleware


def list_agents() -> None:
    """List all available agents."""
    agents_dir = settings.user_deepagents_dir

    if not agents_dir.exists() or not any(agents_dir.iterdir()):
        console.print("[yellow]No agents found.[/yellow]")
        console.print(
            "[dim]Agents will be created in ~/.deepagents/ when you first use them.[/dim]",
            style=COLORS["dim"],
        )
        return

    console.print("\n[bold]Available Agents:[/bold]\n", style=COLORS["primary"])

    for agent_path in sorted(agents_dir.iterdir()):
        if agent_path.is_dir():
            agent_name = agent_path.name
            agent_md = agent_path / "AGENTS.md"

            if agent_md.exists():
                console.print(f"  • [bold]{agent_name}[/bold]", style=COLORS["primary"])
                console.print(f"    {agent_path}", style=COLORS["dim"])
            else:
                console.print(
                    f"  • [bold]{agent_name}[/bold] [dim](incomplete)[/dim]", style=COLORS["tool"]
                )
                console.print(f"    {agent_path}", style=COLORS["dim"])

    console.print()


def reset_agent(agent_name: str, source_agent: str | None = None) -> None:
    """Reset an agent to default or copy from another agent."""
    agents_dir = settings.user_deepagents_dir
    agent_dir = agents_dir / agent_name

    if source_agent:
        source_dir = agents_dir / source_agent
        source_md = source_dir / "AGENTS.md"

        if not source_md.exists():
            console.print(
                f"[bold red]Error:[/bold red] Source agent '{source_agent}' not found "
                "or has no AGENTS.md"
            )
            return

        source_content = source_md.read_text()
        action_desc = f"contents of agent '{source_agent}'"
    else:
        source_content = get_default_coding_instructions()
        action_desc = "default"

    if agent_dir.exists():
        shutil.rmtree(agent_dir)
        console.print(f"Removed existing agent directory: {agent_dir}", style=COLORS["tool"])

    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agent_dir / "AGENTS.md"
    agent_md.write_text(source_content)

    console.print(f"✓ Agent '{agent_name}' reset to {action_desc}", style=COLORS["primary"])
    console.print(f"Location: {agent_dir}\n", style=COLORS["dim"])


def get_system_prompt(assistant_id: str, sandbox_type: str | None = None) -> str:
    """Get the base system prompt for the agent.

    Args:
        assistant_id: The agent identifier for path references
        sandbox_type: Type of sandbox provider ("modal", "runloop", "daytona").
                     If None, agent is operating in local mode.

    Returns:
        The system prompt string (without AGENTS.md content)
    """
    agent_dir_path = f"~/.deepagents/{assistant_id}"

    if sandbox_type:
        # Get provider-specific working directory

        working_dir = get_default_working_dir(sandbox_type)

        working_dir_section = f"""### Current Working Directory

You are operating in a **remote Linux sandbox** at `{working_dir}`.

All code execution and file operations happen in this sandbox environment.

**Important:**
- The CLI is running locally on the user's machine, but you execute code remotely
- Use `{working_dir}` as your working directory for all operations

"""
    else:
        cwd = Path.cwd()
        working_dir_section = f"""### Current Working Directory

The filesystem backend is currently operating in: `{cwd}`

### File System and Paths

**IMPORTANT - Path Handling:**
- You can use **Windows absolute paths directly** (e.g., `E:\\git\\deepagents-book\\novels\\file.md` or `E:/git/deepagents-book/novels/file.md`)
- You can also use **virtual paths** starting with `/` (e.g., `/file.txt`, `/research_project/file.md`)
- Virtual paths are relative to the current working directory: `{cwd}`
- Example: To access `{cwd}/research_project/file.md`, use the virtual path `/research_project/file.md`
- Example: To access `{cwd}/file.txt`, use the virtual path `/file.txt`
- **For files outside current working directory**: Use Windows absolute paths directly (e.g., `E:\\git\\deepagents-book\\novels\\file.md`)
- **Path format**: You can use either backslashes (`\\`) or forward slashes (`/`) in Windows paths - both work
- **Never use relative paths** without leading `/` - always start virtual paths with `/` or use absolute paths

"""

    return (
        working_dir_section
        + f"""### Skills Directory

Your skills are stored at: `{agent_dir_path}/skills/`
Skills may contain scripts or supporting files. When executing skill scripts, use the real filesystem path:
Example: `python {agent_dir_path}/skills/web-research/script.py`

### Human-in-the-Loop Tool Approval

Some tool calls require user approval before execution. When a tool call is rejected by the user:
1. Accept their decision immediately - do NOT retry the same command
2. Explain that you understand they rejected the action
3. Suggest an alternative approach or ask for clarification
4. Never attempt the exact same rejected command again

Respect the user's decisions and work with them collaboratively.

### Web Search Tool Usage

When you use the web_search tool:
1. The tool will return search results with titles, URLs, and content excerpts
2. You MUST read and process these results, then respond naturally to the user
3. NEVER show raw JSON or tool results directly to the user
4. Synthesize the information from multiple sources into a coherent answer
5. Cite your sources by mentioning page titles or URLs when relevant
6. If the search doesn't find what you need, explain what you found and ask clarifying questions

The user only sees your text responses - not tool results. Always provide a complete, natural language answer after using web_search.

### Todo List Management

When using the write_todos tool:
1. Keep the todo list MINIMAL - aim for 3-6 items maximum
2. Only create todos for complex, multi-step tasks that truly need tracking
3. Break down work into clear, actionable items without over-fragmenting
4. For simple tasks (1-2 steps), just do them directly without creating todos
5. When first creating a todo list for a task, ALWAYS ask the user if the plan looks good before starting work
   - Create the todos, let them render, then ask: "Does this plan look good?" or similar
   - Wait for the user's response before marking the first todo as in_progress
   - If they want changes, adjust the plan accordingly
6. Update todo status promptly as you complete each item

The todo list is a planning tool - use it judiciously to avoid overwhelming the user with excessive task tracking."""
    )


def _format_write_file_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format write_file tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    content = args.get("content", "")

    action = "Overwrite" if Path(file_path).exists() else "Create"
    line_count = len(content.splitlines())

    return f"File: {file_path}\nAction: {action} file\nLines: {line_count}"


def _format_edit_file_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format edit_file tool call for approval prompt."""
    args = tool_call["args"]
    file_path = args.get("file_path", "unknown")
    replace_all = bool(args.get("replace_all", False))

    return (
        f"File: {file_path}\n"
        f"Action: Replace text ({'all occurrences' if replace_all else 'single occurrence'})"
    )


def _format_web_search_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format web_search tool call for approval prompt."""
    args = tool_call["args"]
    query = args.get("query", "unknown")
    max_results = args.get("max_results", 5)

    return f"Query: {query}\nMax results: {max_results}\n\n⚠️  This will use Tavily API credits"


def _format_fetch_url_description(
    tool_call: ToolCall, _state: AgentState, _runtime: Runtime
) -> str:
    """Format fetch_url tool call for approval prompt."""
    args = tool_call["args"]
    url = args.get("url", "unknown")
    timeout = args.get("timeout", 30)

    return f"URL: {url}\nTimeout: {timeout}s\n\n⚠️  Will fetch and convert web content to markdown"


def _format_task_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format task (subagent) tool call for approval prompt.

    The task tool signature is: task(description: str, subagent_type: str)
    The description contains all instructions that will be sent to the subagent.
    """
    args = tool_call["args"]
    description = args.get("description", "unknown")
    subagent_type = args.get("subagent_type", "unknown")

    # Truncate description if too long for display
    description_preview = description
    if len(description) > 500:
        description_preview = description[:500] + "..."

    return (
        f"Subagent Type: {subagent_type}\n\n"
        f"Task Instructions:\n"
        f"{'─' * 40}\n"
        f"{description_preview}\n"
        f"{'─' * 40}\n\n"
        f"⚠️  Subagent will have access to file operations and shell commands"
    )


def _format_shell_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format shell tool call for approval prompt."""
    args = tool_call["args"]
    command = args.get("command", "N/A")
    return f"Shell Command: {command}\nWorking Directory: {Path.cwd()}"


def _format_execute_description(tool_call: ToolCall, _state: AgentState, _runtime: Runtime) -> str:
    """Format execute tool call for approval prompt."""
    args = tool_call["args"]
    command = args.get("command", "N/A")
    return f"Execute Command: {command}\nLocation: Remote Sandbox"


def _add_interrupt_on() -> dict[str, InterruptOnConfig]:
    """Configure human-in-the-loop interrupt_on settings for destructive tools."""
    shell_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_shell_description,
    }

    execute_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_execute_description,
    }

    write_file_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_write_file_description,
    }

    edit_file_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_edit_file_description,
    }

    web_search_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_web_search_description,
    }

    fetch_url_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_fetch_url_description,
    }

    task_interrupt_config: InterruptOnConfig = {
        "allowed_decisions": ["approve", "reject"],
        "description": _format_task_description,
    }
    return {
        "shell": shell_interrupt_config,
        "execute": execute_interrupt_config,
        "write_file": write_file_interrupt_config,
        "edit_file": edit_file_interrupt_config,
        "web_search": web_search_interrupt_config,
        "fetch_url": fetch_url_interrupt_config,
        "task": task_interrupt_config,
    }


def create_cli_agent(
    model: str | BaseChatModel,
    assistant_id: str,
    *,
    tools: list[BaseTool] | None = None,
    sandbox: SandboxBackendProtocol | None = None,
    sandbox_type: str | None = None,
    system_prompt: str | None = None,
    auto_approve: bool = False,
    enable_memory: bool = True,
    enable_skills: bool = True,
    enable_shell: bool = True,
    checkpointer: BaseCheckpointSaver | None = None,
) -> tuple[Pregel, CompositeBackend]:
    """Create a CLI-configured agent with flexible options.

    This is the main entry point for creating a deepagents CLI agent, usable both
    internally and from external code (e.g., benchmarking frameworks, Harbor).

    Args:
        model: LLM model to use (e.g., "anthropic:claude-sonnet-4-5-20250929")
        assistant_id: Agent identifier for memory/state storage
        tools: Additional tools to provide to agent
        sandbox: Optional sandbox backend for remote execution (e.g., ModalBackend).
                 If None, uses local filesystem + shell.
        sandbox_type: Type of sandbox provider ("modal", "runloop", "daytona").
                     Used for system prompt generation.
        system_prompt: Override the default system prompt. If None, generates one
                      based on sandbox_type and assistant_id.
        auto_approve: If True, automatically approves all tool calls without human
                     confirmation. Useful for automated workflows.
        enable_memory: Enable MemoryMiddleware for persistent memory
        enable_skills: Enable SkillsMiddleware for custom agent skills
        enable_shell: Enable ShellMiddleware for local shell execution (only in local mode)
        checkpointer: Optional checkpointer for session persistence. If None, uses
                     InMemorySaver (no persistence across CLI invocations).

    Returns:
        2-tuple of (agent_graph, backend)
        - agent_graph: Configured LangGraph Pregel instance ready for execution
        - composite_backend: CompositeBackend for file operations
    """
    tools = tools or []

    # Setup agent directory for persistent memory (if enabled)
    if enable_memory or enable_skills:
        agent_dir = settings.ensure_agent_dir(assistant_id)
        agent_md = agent_dir / "AGENTS.md"
        if not agent_md.exists():
            source_content = get_default_coding_instructions()
            agent_md.write_text(source_content)

    # Skills directories (if enabled)
    skills_dir = None
    project_skills_dir = None
    builtin_skills_dir = None
    if enable_skills:
        skills_dir = settings.ensure_user_skills_dir(assistant_id)
        project_skills_dir = settings.get_project_skills_dir()
        builtin_skills_dir = settings.get_builtin_skills_dir()
        # Auto-extract .skill files in builtin skills directory
        extract_builtin_skills()

    # Build middleware stack based on enabled features
    agent_middleware = []

    # Add prompt optimizer middleware (should run early to optimize prompts before processing)
    # This ensures prompts are optimized before write_todos or other operations
    # always_optimize=True: 每次输入都先调用 prompt-optimizer 技能优化提示词
    agent_middleware.append(PromptOptimizerMiddleware(auto_optimize=True, always_optimize=True))

    # Add memory middleware
    if enable_memory:
        # Create factory function for memory backend with Windows path support
        def create_memory_backend(runtime):
            routes = {}
            
            # 用户 memory 文件
            user_memory_path = settings.get_user_agent_md_path(assistant_id)
            if user_memory_path:
                # 为 memory 文件创建 backend，使用父目录作为 root_dir
                user_memory_dir = user_memory_path.parent
                user_memory_backend = FilesystemBackend(root_dir=str(user_memory_dir), virtual_mode=True)
                routes["/memory/user/"] = user_memory_backend
            
            # 项目 memory 文件
            project_agent_md = settings.get_project_agent_md_path()
            if project_agent_md:
                project_memory_dir = project_agent_md.parent
                project_memory_backend = FilesystemBackend(root_dir=str(project_memory_dir), virtual_mode=True)
                routes["/memory/project/"] = project_memory_backend
            
            # 创建 CompositeBackend
            if routes:
                return CompositeBackend(
                    default=StateBackend(runtime),
                    routes=routes
                )
            else:
                # 如果没有 routes，使用 StateBackend
                return StateBackend(runtime)
        
        # 获取 memory sources（虚拟路径）
        memory_sources = []
        if settings.get_user_agent_md_path(assistant_id):
            memory_sources.append("/memory/user/AGENTS.md")
        project_agent_md = settings.get_project_agent_md_path()
        if project_agent_md:
            memory_sources.append("/memory/project/AGENTS.md")
        
        if memory_sources:
            agent_middleware.append(
                MemoryMiddleware(
                    backend=create_memory_backend,
                    sources=memory_sources,
                )
            )

    # Add skills middleware
    if enable_skills:
        # 统一使用内置技能目录，所有技能都在 libs/deepagents-cli/deepagents_cli/skills 管理
        if builtin_skills_dir and builtin_skills_dir.exists():
            def create_skills_backend(runtime):
                # 创建指向技能目录的 backend
                skills_backend = FilesystemBackend(root_dir=str(builtin_skills_dir), virtual_mode=True)
                return CompositeBackend(
                    default=StateBackend(runtime),
                    routes={"/skills/": skills_backend}
                )
            
            agent_middleware.append(
                SkillsMiddleware(
                    backend=create_skills_backend,
                    sources=["/skills/"],
                )
            )

    # CONDITIONAL SETUP: Local vs Remote Sandbox
    if sandbox is None:
        # ========== LOCAL MODE ==========
        backend = FilesystemBackend()  # Current working directory

        # Local context middleware (git info, directory tree, etc.)
        agent_middleware.append(LocalContextMiddleware())
        
        # Novel prompt middleware (detects novel-related content and injects prompt)
        agent_middleware.append(NovelPromptMiddleware())

        # Add shell middleware (only in local mode)
        if enable_shell:
            # Create environment for shell commands
            # Restore user's original LANGSMITH_PROJECT so their code traces separately
            shell_env = os.environ.copy()
            if settings.user_langchain_project:
                shell_env["LANGSMITH_PROJECT"] = settings.user_langchain_project

            agent_middleware.append(
                ShellMiddleware(
                    workspace_root=str(Path.cwd()),
                    env=shell_env,
                )
            )
    else:
        # ========== REMOTE SANDBOX MODE ==========
        backend = sandbox  # Remote sandbox (ModalBackend, etc.)
        # Note: Shell middleware not used in sandbox mode
        # File operations and execute tool are provided by the sandbox backend
        
        # Novel prompt middleware (also available in sandbox mode)
        agent_middleware.append(NovelPromptMiddleware())

    # Get or use custom system prompt
    if system_prompt is None:
        system_prompt = get_system_prompt(assistant_id=assistant_id, sandbox_type=sandbox_type)

    # Configure interrupt_on based on auto_approve setting
    if auto_approve:
        # No interrupts - all tools run automatically
        interrupt_on = {}
    else:
        # Full HITL for destructive operations
        interrupt_on = _add_interrupt_on()

    # Add skills route to main backend so file tools can access skill files
    # Note: CompositeBackend routes need backend instances, not factory functions
    # We'll create a factory function for the composite backend itself
    def create_composite_backend_with_skills(runtime):
        """Factory function to create CompositeBackend with skills route."""
        routes = {}
        if enable_skills and builtin_skills_dir and builtin_skills_dir.exists():
            # 统一使用 /skills/ 路径，指向 libs/deepagents-cli/deepagents_cli/skills
            skills_backend = FilesystemBackend(root_dir=str(builtin_skills_dir), virtual_mode=True)
            routes["/skills/"] = skills_backend
        
        # Resolve default backend (could be a factory function)
        if callable(backend):
            default_backend = backend(runtime)
        else:
            default_backend = backend
        
        return CompositeBackend(default=default_backend, routes=routes)
    
    # Use factory function for composite backend
    composite_backend = create_composite_backend_with_skills

    # Create the agent
    # Use provided checkpointer or fallback to InMemorySaver
    final_checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        backend=composite_backend,
        middleware=agent_middleware,
        interrupt_on=interrupt_on,
        checkpointer=final_checkpointer,
    ).with_config(config)
    return agent, composite_backend


def create_novel_agent(
    model: str | BaseChatModel,
    project_path: Path,
    project_title: str,
    world_type: str,
    *,
    tools: list[BaseTool] | None = None,
    system_prompt: str | None = None,
    auto_approve: bool = False,
    checkpointer: BaseCheckpointSaver | None = None,
) -> tuple[Pregel, CompositeBackend]:
    """Create a novel writing agent with conversation-driven workflow.

    This creates a single agent with all novel-related skills injected,
    following the "Pure Skill" pattern where context is fully shared and
    capabilities are injected via Skills rather than SubAgents.

    Memory System:
    - Auto Layer: Project metadata, progress (injected via NovelMemoryMiddleware)
    - Active Layer: Agent-managed via remember/recall/forget tools
    - File Layer: Long content (outlines, chapters) stored as files

    Args:
        model: LLM model to use (e.g., "anthropic:claude-sonnet-4-5-20250929")
        project_path: Path to the novel project directory
        project_title: Title of the novel
        world_type: World type (onepiece/naruto/original)
        tools: Additional tools to provide to agent
        system_prompt: Override the default system prompt
        auto_approve: If True, auto-approve all tool calls
        checkpointer: Optional checkpointer for session persistence

    Returns:
        2-tuple of (agent_graph, backend)
    """
    # Import memory tools and middleware
    from deepagents_cli.novel.memory_middleware import NovelMemoryMiddleware
    from deepagents_cli.novel.memory_tools import get_all_memory_tools, init_memory_store
    from deepagents_cli.novel.project import NovelProject

    tools = list(tools) if tools else []

    # Add memory tools
    memory_tools = get_all_memory_tools()
    tools.extend(memory_tools)

    # Initialize memory store for this project
    init_memory_store(project_path)

    # Load or create NovelProject
    try:
        project = NovelProject.load(project_path)
    except FileNotFoundError:
        # Project doesn't exist, create minimal config
        project = NovelProject(project_path)
        project._config = project._load_config()
        project._state = project._load_state()

    # Generate assistant_id from project title for memory storage
    assistant_id = f"novel-{project_title.replace(' ', '-').lower()}"

    # Setup agent directory for memory
    agent_dir = settings.ensure_agent_dir(assistant_id)
    agent_md = agent_dir / "AGENTS.md"
    if not agent_md.exists():
        # Initialize with novel-specific memory template
        novel_memory = f"""# 小说项目记忆: {project_title}

## 项目信息
- 标题: {project_title}
- 世界观: {world_type}
- 项目路径: {project_path}

## 作者偏好
（随着创作过程自动记录）

## 创作决策
（重要的剧情选择会记录在这里）
"""
        agent_md.write_text(novel_memory, encoding="utf-8")

    # Get builtin skills directory
    builtin_skills_dir = settings.get_builtin_skills_dir()

    # Build middleware stack
    agent_middleware = []

    # Add prompt optimizer middleware
    agent_middleware.append(PromptOptimizerMiddleware(auto_optimize=True, always_optimize=True))

    # Add memory middleware for author preferences
    def create_memory_backend(runtime):
        routes = {}
        user_memory_path = settings.get_user_agent_md_path(assistant_id)
        if user_memory_path:
            user_memory_dir = user_memory_path.parent
            user_memory_backend = FilesystemBackend(root_dir=str(user_memory_dir), virtual_mode=True)
            routes["/memory/user/"] = user_memory_backend

        if routes:
            return CompositeBackend(
                default=StateBackend(runtime),
                routes=routes
            )
        return StateBackend(runtime)

    memory_sources = []
    if settings.get_user_agent_md_path(assistant_id):
        memory_sources.append("/memory/user/AGENTS.md")

    if memory_sources:
        agent_middleware.append(
            MemoryMiddleware(
                backend=create_memory_backend,
                sources=memory_sources,
            )
        )

    # Add skills middleware with novel-related skills
    if builtin_skills_dir and builtin_skills_dir.exists():
        def create_skills_backend(runtime):
            skills_backend = FilesystemBackend(root_dir=str(builtin_skills_dir), virtual_mode=True)
            return CompositeBackend(
                default=StateBackend(runtime),
                routes={"/skills/": skills_backend}
            )

        agent_middleware.append(
            SkillsMiddleware(
                backend=create_skills_backend,
                sources=["/skills/"],
            )
        )

    # Add local context middleware
    agent_middleware.append(LocalContextMiddleware())

    # Add novel prompt middleware
    agent_middleware.append(NovelPromptMiddleware())

    # Add novel memory middleware (auto-injects project state and memory summary)
    agent_middleware.append(NovelMemoryMiddleware(project=project))

    # Use FilesystemBackend pointing to project directory
    project_backend = FilesystemBackend(root_dir=str(project_path), virtual_mode=True)

    # Add summarization middleware for context compression
    # Uses NovelSummarizationConfig for novel-specific summarization
    from deepagents_cli.novel.memory_middleware import NovelSummarizationConfig
    summarization_config = NovelSummarizationConfig(
        max_tokens=100000,  # Trigger summarization at 100k tokens
        preserve_recent=10,  # Keep last 10 messages
    )

    def create_summarization_backend(runtime):
        """Backend for storing conversation history during summarization."""
        return project_backend

    agent_middleware.append(
        SummarizationMiddleware(
            model=model,
            backend=create_summarization_backend,
            trigger=("tokens", summarization_config.max_tokens),
            keep=("messages", summarization_config.preserve_recent),
            summary_prompt=summarization_config.summary_instruction,
            history_path_prefix="/.novel/conversation_history",
        )
    )

    # Build system prompt with project context
    if system_prompt is None:
        system_prompt = _get_novel_system_prompt(
            project_path=project_path,
            project_title=project_title,
            world_type=world_type,
            assistant_id=assistant_id,
        )

    # Configure interrupt_on based on auto_approve
    if auto_approve:
        interrupt_on = {}
    else:
        interrupt_on = _add_interrupt_on()

    # Create composite backend with skills route
    def create_novel_composite_backend(runtime):
        routes = {}
        if builtin_skills_dir and builtin_skills_dir.exists():
            skills_backend = FilesystemBackend(root_dir=str(builtin_skills_dir), virtual_mode=True)
            routes["/skills/"] = skills_backend

        return CompositeBackend(default=project_backend, routes=routes)

    # Create the agent
    final_checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        backend=create_novel_composite_backend,
        middleware=agent_middleware,
        interrupt_on=interrupt_on,
        checkpointer=final_checkpointer,
    ).with_config(config)

    return agent, create_novel_composite_backend


def _get_novel_system_prompt(
    project_path: Path,
    project_title: str,
    world_type: str,
    assistant_id: str,
) -> str:
    """Generate system prompt for novel writing agent.

    Args:
        project_path: Path to novel project
        project_title: Title of the novel
        world_type: World type (onepiece/naruto/original)
        assistant_id: Agent identifier

    Returns:
        System prompt string
    """
    agent_dir_path = f"~/.deepagents/{assistant_id}"

    return f"""### 小说创作会话

你正在帮助用户创作小说《{project_title}》。

**项目信息**:
- 标题: {project_title}
- 世界观: {world_type}
- 项目路径: {project_path}

**你的角色**:
你是一位经验丰富的小说编辑和创作顾问，通过自然语言对话帮助用户完成小说创作。

**核心原则**:
1. **提供选择而非开放问题**: 当需要用户决策时，提供2-4个具体选项
2. **主动提供创意建议**: 不要被动等待，要主动推进创作进度
3. **渐进式确认**: 每个重要步骤都需要用户确认后再继续
4. **记住上下文**: 不要让用户重复已经说过的设定

**文件操作**:
- 项目文件在当前工作目录（虚拟路径以 `/` 开头）
- 大纲保存在 `/outline/` 目录
- 正文保存在 `/chapters/` 目录
- 角色档案在 `/world/characters/` 目录

**Skills目录**:
你的技能文件在: `{agent_dir_path}/skills/`

**工具使用**:
- 使用 `read_file` 读取项目文件
- 使用 `write_file` 保存创作内容
- 使用 `edit_file` 修改已有内容
- 禁止使用 shell 命令进行文件操作

**对话风格**:
- 像一个有经验的编辑在和作者聊天
- 尊重用户的创意选择
- 在关键节点总结已确定的内容
- 遇到创作瓶颈时主动提供建议

### Human-in-the-Loop Tool Approval

某些工具调用需要用户批准。当工具调用被拒绝时:
1. 立即接受用户的决定 - 不要重试相同的命令
2. 解释你理解他们拒绝了该操作
3. 建议替代方案或询问澄清
4. 永远不要再次尝试完全相同的被拒绝命令

### Todo List Management

使用 write_todos 工具时:
1. 保持待办列表简洁 - 最多3-6项
2. 只为真正需要跟踪的复杂任务创建待办
3. 对于简单任务（1-2步），直接执行而不创建待办
4. 首次为任务创建待办列表时，始终询问用户计划是否合适
"""
