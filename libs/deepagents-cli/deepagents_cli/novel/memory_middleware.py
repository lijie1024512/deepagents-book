"""Novel Memory Middleware.

This middleware manages the automatic memory layer for novel writing:
1. Injects project metadata into system prompt
2. Injects memory summary into system prompt
3. Loads phase-specific Skill content based on current_phase
4. Manages context compression for long conversations
5. Auto-extracts important info from tool results (optional)
6. Integrates Hooks system for automatic context management (inspired by planning-with-files)

The Hooks system provides:
- PreToolUse: Auto-read relevant context before write operations
- PostToolUse: Remind to update progress/check foreshadows after chapter completion
- Auto-checkpoint: Create checkpoints after significant operations
- Session Recovery: 5-Question context reconstruction for interrupted sessions
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langgraph.runtime import Runtime

from deepagents.middleware._utils import append_to_system_message

from deepagents_cli.novel.hooks import (
    NovelHooksRegistry,
    build_hooks_system_prompt_section,
    init_hooks,
)
from deepagents_cli.novel.memory_tools import PHASE_LABELS, get_memory_summary, init_memory_store

if TYPE_CHECKING:
    from deepagents_cli.novel.project import NovelProject

logger = logging.getLogger(__name__)


class NovelMemoryMiddleware(AgentMiddleware):
    """Middleware for managing novel writing memory and hooks.

    This middleware:
    1. Initializes memory store for the project
    2. Injects project state and memory summary into system prompt
    3. Provides context for the agent without requiring explicit recall
    4. Manages the Hooks system for automatic context and reminders

    The memory is organized in layers:
    - Auto Layer: Project metadata, progress (injected automatically)
    - Active Layer: Agent-managed via remember/recall/forget tools
    - File Layer: Long content (outlines, chapters) stored as files

    The Hooks system (inspired by planning-with-files):
    - Automatically gathers context before major operations
    - Provides reminders after chapter/outline completion
    - Creates checkpoints after significant operations
    - Offers session recovery context for interrupted sessions
    """

    def __init__(
        self,
        project: "NovelProject",
        max_context_tokens: int = 100000,
        preserve_recent_messages: int = 10,
        enable_hooks: bool = True,
    ):
        """Initialize the middleware.

        Args:
            project: The NovelProject instance
            max_context_tokens: Maximum context tokens before compression
            preserve_recent_messages: Number of recent messages to preserve during compression
            enable_hooks: Whether to enable the Hooks system (default: True)
        """
        super().__init__()
        self.project = project
        self.max_context_tokens = max_context_tokens
        self.preserve_recent_messages = preserve_recent_messages
        self.enable_hooks = enable_hooks
        self._is_first_call = True  # Track if this is the first call (for session recovery)
        self._skill_cache: dict[str, str] = {}  # Cache for loaded skill files

        self._prompt_call_count = 0  # Counter for prompt logging

        # Initialize memory store
        init_memory_store(project.path)

        # Initialize hooks registry
        if enable_hooks:
            self.hooks_registry = NovelHooksRegistry(project.path)
            init_hooks(project.path)
        else:
            self.hooks_registry = None

    def _load_skill_file(self, skill_name: str) -> str:
        """Load a SKILL.md file by skill name, with caching.

        Args:
            skill_name: e.g. "novel-orchestrator", "novel-phase-brainstorm"

        Returns:
            Content of the SKILL.md file, or empty string if not found.
        """
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]

        # Look in the builtin skills directory
        skills_dir = Path(__file__).parent.parent / "skills"
        skill_path = skills_dir / skill_name / "SKILL.md"

        content = ""
        if skill_path.exists():
            try:
                content = skill_path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Failed to read skill file: %s", skill_path)

        self._skill_cache[skill_name] = content
        return content

    def _load_phase_references(self, skill_content: str) -> str:
        """Load inject_references from a skill's frontmatter.

        Args:
            skill_content: The full SKILL.md content with YAML frontmatter

        Returns:
            Concatenated reference file contents
        """
        # Simple frontmatter parsing for inject_references
        if not skill_content.startswith("---"):
            return ""

        # Find the closing --- of frontmatter
        end_idx = skill_content.index("---", 3)
        frontmatter = skill_content[3:end_idx]

        # Look for inject_references list
        refs = []
        in_refs = False
        for line in frontmatter.split("\n"):
            stripped = line.strip()
            if stripped.startswith("inject_references:"):
                val = stripped[len("inject_references:") :].strip()
                if val == "[]":
                    return ""
                in_refs = True
                continue
            if in_refs:
                if stripped.startswith("- "):
                    refs.append(stripped[2:].strip())
                elif not stripped.startswith("#") and stripped:
                    in_refs = False

        if not refs:
            return ""

        # Load each reference file
        skills_dir = Path(__file__).parent.parent / "skills"
        parts = []
        for ref in refs:
            # ref is relative to the skill directory, find it
            for skill_dir in skills_dir.iterdir():
                ref_path = skill_dir / ref
                if ref_path.exists():
                    try:
                        parts.append(ref_path.read_text(encoding="utf-8"))
                    except OSError:
                        pass
                    break

        return "\n\n".join(parts)

    # Mapping from world_type to knowledge base filename
    _WORLD_KNOWLEDGE_FILES: ClassVar[dict[str, str]] = {
        "onepiece": "onepiece_knowledge_base.md",
        "naruto": "naruto-world.md",
        "bleach": "bleach-world.md",
    }

    def _load_world_knowledge(self, world_type: str) -> str:
        """Load world knowledge base file for the given world type.

        Args:
            world_type: e.g. "onepiece", "naruto", "bleach", "original"

        Returns:
            Formatted world knowledge content, or empty string if not applicable.
        """
        filename = self._WORLD_KNOWLEDGE_FILES.get(world_type)
        if not filename:
            return ""

        # Check cache first
        cache_key = f"world_knowledge:{world_type}"
        if cache_key in self._skill_cache:
            return self._skill_cache[cache_key]

        refs_dir = (
            Path(__file__).parent.parent / "skills" / "novel-outline-generator" / "references"
        )
        knowledge_path = refs_dir / filename

        content = ""
        if knowledge_path.exists():
            try:
                raw = knowledge_path.read_text(encoding="utf-8")
                content = f"【世界观知识库】\n{raw}"
            except OSError:
                logger.warning("Failed to read world knowledge file: %s", knowledge_path)

        self._skill_cache[cache_key] = content
        return content

    def _build_auto_context(self) -> str:
        """Build the automatic context injection.

        This includes:
        - Project metadata
        - Current progress and phase
        - Phase-specific Skill content (orchestrator + current phase)
        - Character states (from project state)
        - Memory summary (from agent memory)
        """
        config = self.project.config
        state = self.project.state

        parts = []

        # Project metadata
        world_display = config.world_type if config.world_type != "unset" else "未指定"
        phase_label = PHASE_LABELS.get(state.current_phase, state.current_phase)
        parts.append(f"""【项目信息】
- 小说: 《{config.title}》
- 世界观: {world_display}
- 项目路径: {self.project.path}""")

        # Progress with phase
        parts.append(f"""
【创作进度】
- 当前阶段: {phase_label} ({state.current_phase})
- 大纲: {state.outline_completed}/{state.outline_total or "?"} 章
- 正文: {state.writing_completed}/{state.writing_total or "?"} 章
- 当前章节: 第 {state.current_chapter} 章""")

        # Load and inject phase-specific Skills
        # 1. Always load orchestrator
        orchestrator_content = self._load_skill_file("novel-orchestrator")
        if orchestrator_content:
            parts.append(f"\n{orchestrator_content}")

        # 2. Load current phase skill
        phase_skill_name = f"novel-phase-{state.current_phase}"
        phase_content = self._load_skill_file(phase_skill_name)
        if phase_content:
            parts.append(f"\n{phase_content}")
            # 3. Load any inject_references from the phase skill
            refs_content = self._load_phase_references(phase_content)
            if refs_content:
                parts.append(f"\n{refs_content}")

        # 4. Load world knowledge based on world_type
        world_content = self._load_world_knowledge(config.world_type)
        if world_content:
            parts.append(f"\n{world_content}")

        # Character states from project state
        if state.characters:
            char_lines = ["", "【角色状态】(来自项目状态)"]
            for name, char in state.characters.items():
                char_lines.append(f"- {name}: {char.status}，位置: {char.location}")
            parts.append("\n".join(char_lines))

        # Pending foreshadowing from project state
        pending = [f for f in state.foreshadowing if not f.get("resolved", False)]
        if pending:
            foreshadow_lines = ["", f"【待回收伏笔】(来自项目状态，共{len(pending)}个)"]
            for f in pending[:5]:
                foreshadow_lines.append(f"- 第{f['chapter']}章: {f['content'][:30]}...")
            if len(pending) > 5:
                foreshadow_lines.append(f"- ...还有 {len(pending) - 5} 个")
            parts.append("\n".join(foreshadow_lines))

        # Memory summary from agent memory
        memory_summary = get_memory_summary()
        if memory_summary:
            parts.append("")
            parts.append(memory_summary)

        # Minimal tool hint (detailed docs are in each tool's own description)
        parts.append("""【可用工具速查】
- 记忆: remember / recall / forget / update_memory
- 角色: update_character / get_character / list_characters / add_relationship
- 伏笔: plant_foreshadow / resolve_foreshadow / list_foreshadows
- 进度: get_progress / update_progress / advance_phase
- 章节: complete_chapter / complete_outline
""")

        # Add hooks system information only for writing/outline phases
        # (hooks are about chapter/outline pre/post context — irrelevant for brainstorm/engine/character)
        if self.hooks_registry and state.current_phase in ("outline", "writing", "revision"):
            parts.append(build_hooks_system_prompt_section(self.hooks_registry))

        return "\n".join(parts)

    def before_agent(
        self,
        state: AgentState,
        runtime: Runtime[Any],
        config: Any = None,
    ) -> dict[str, Any] | None:
        """Before agent runs, inject session recovery context if needed.

        This implements the "5-Question Reboot Check" from planning-with-files:
        1. Where am I? - Current progress
        2. What was I doing? - Last operations
        3. What have I discovered? - Memory entries
        4. What's left to do? - Pending items
        5. What problems emerged? - Issues check

        Args:
            state: Current agent state
            runtime: LangGraph runtime
            config: Optional config

        Returns:
            State updates if needed, None otherwise
        """
        # Only inject recovery context on first call of session
        if not self._is_first_call or not self.hooks_registry:
            return None

        self._is_first_call = False

        # Get session recovery context
        recovery_context = self.hooks_registry.get_recovery_context()
        if not recovery_context:
            return None

        # Check if there are any messages yet (don't inject on truly fresh session)
        messages = state.get("messages", [])
        if len(messages) <= 1:
            # Fresh session, no recovery needed
            return None

        # Inject recovery context as a system reminder in the messages
        # This helps the agent understand where the session left off
        from langchain_core.messages import SystemMessage

        recovery_message = SystemMessage(
            content=f"<session-recovery>\n{recovery_context}\n</session-recovery>"
        )

        # Prepend to messages (after any existing system message)
        new_messages = list(messages)
        # Find first non-system message to insert after
        insert_idx = 0
        for i, msg in enumerate(new_messages):
            if msg.type == "system":
                insert_idx = i + 1
            else:
                break

        new_messages.insert(insert_idx, recovery_message)

        return {"messages": new_messages}

    @staticmethod
    def _extract_message_text(msg: Any) -> str:
        """Extract readable text from a langchain message."""
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
            return "\n".join(text_parts)
        return str(content)

    def _log_prompt(self, request: ModelRequest) -> None:
        """Log the full request sent to the LLM for debugging.

        Writes system message + all conversation messages to
        .novel/logs/prompts-{date}.md.

        Args:
            request: The final ModelRequest after all middleware injections.
        """
        try:
            log_dir = Path(self.project.path) / ".novel" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            self._prompt_call_count += 1
            _CST = timezone(timedelta(hours=8))
            now = datetime.now(_CST)
            date_str = now.strftime("%Y-%m-%d")
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

            log_file = log_dir / f"prompts-{date_str}.md"

            parts: list[str] = []

            # Header
            parts.append(f"\n{'=' * 80}")
            parts.append(f"## Call #{self._prompt_call_count} [{timestamp}]")
            parts.append(f"{'=' * 80}\n")

            # System message
            if request.system_message is not None:
                parts.append("### System Message\n")
                parts.append(self._extract_message_text(request.system_message))
                parts.append("")

            # Conversation messages (user, assistant, tool results)
            if request.messages:
                parts.append(f"### Messages ({len(request.messages)})\n")
                for i, msg in enumerate(request.messages):
                    msg_type = getattr(msg, "type", type(msg).__name__)
                    text = self._extract_message_text(msg)

                    # Tool calls on AI messages
                    tool_calls = getattr(msg, "tool_calls", None)
                    tool_info = ""
                    if tool_calls:
                        names = [tc.get("name", "?") for tc in tool_calls]
                        tool_info = f" [tool_calls: {', '.join(names)}]"

                    parts.append(f"#### [{i}] {msg_type}{tool_info}\n")
                    # Truncate very long messages to keep log manageable
                    if len(text) > 5000:
                        parts.append(text[:5000])
                        parts.append(f"\n... (truncated, total {len(text)} chars)")
                    else:
                        parts.append(text)
                    parts.append("")

            # Tool names
            if hasattr(request, "tools") and request.tools:
                tool_names = []
                for t in request.tools:
                    name = t.name if hasattr(t, "name") else t.get("name", "?")
                    tool_names.append(name)
                parts.append(f"### Tools ({len(tool_names)})\n")
                parts.append(", ".join(tool_names))
                parts.append("")

            parts.append("")

            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n".join(parts))

        except Exception:
            logger.debug("Failed to log prompt", exc_info=True)

    def _get_modified_request(self, request: ModelRequest) -> ModelRequest:
        """Inject auto context into system prompt."""
        auto_context = self._build_auto_context()

        new_system_message = append_to_system_message(request.system_message, auto_context)

        return request.override(system_message=new_system_message)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject context and handle the request."""
        modified_request = self._get_modified_request(request)
        self._log_prompt(modified_request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject context and handle the request."""
        modified_request = self._get_modified_request(request)
        self._log_prompt(modified_request)
        return await handler(modified_request)


class NovelSummarizationConfig:
    """Configuration for novel-specific summarization.

    This config is used with SummarizationMiddleware to provide
    novel-aware context compression.
    """

    def __init__(
        self,
        max_tokens: int = 100000,
        preserve_recent: int = 10,
        summary_instruction: str | None = None,
    ):
        """Initialize summarization config.

        Args:
            max_tokens: Maximum context tokens before triggering summarization
            preserve_recent: Number of recent messages to preserve
            summary_instruction: Custom instruction for summarization
        """
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent
        self.summary_instruction = summary_instruction or self._default_instruction()

    def _default_instruction(self) -> str:
        """Default summarization instruction for novel writing."""
        return """请总结以上对话历史，重点保留：
1. 用户的创作决策（选择的剧情分支、角色设定）
2. 已确定的剧情走向
3. 角色状态变化
4. 埋下的伏笔
5. 用户的偏好和风格要求

保持摘要简洁但信息完整，以便继续创作时参考。"""

    def to_dict(self) -> dict:
        """Convert to dict for SummarizationMiddleware."""
        return {
            "max_tokens": self.max_tokens,
            "preserve_recent": self.preserve_recent,
            "summary_instruction": self.summary_instruction,
        }


__all__ = [
    "NovelMemoryMiddleware",
    "NovelSummarizationConfig",
    "NovelHooksRegistry",
]

# Re-export from hooks for convenience
from deepagents_cli.novel.hooks import NovelHooksRegistry
