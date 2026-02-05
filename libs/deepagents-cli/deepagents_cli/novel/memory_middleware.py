"""Novel Memory Middleware.

This middleware manages the automatic memory layer for novel writing:
1. Injects project metadata into system prompt
2. Injects memory summary into system prompt
3. Manages context compression for long conversations
4. Auto-extracts important info from tool results (optional)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)

from deepagents.middleware._utils import append_to_system_message

from deepagents_cli.novel.memory_tools import get_memory_summary, init_memory_store

if TYPE_CHECKING:
    from deepagents_cli.novel.project import NovelProject


class NovelMemoryMiddleware(AgentMiddleware):
    """Middleware for managing novel writing memory.

    This middleware:
    1. Initializes memory store for the project
    2. Injects project state and memory summary into system prompt
    3. Provides context for the agent without requiring explicit recall

    The memory is organized in layers:
    - Auto Layer: Project metadata, progress (injected automatically)
    - Active Layer: Agent-managed via remember/recall/forget tools
    - File Layer: Long content (outlines, chapters) stored as files
    """

    def __init__(
        self,
        project: "NovelProject",
        max_context_tokens: int = 100000,
        preserve_recent_messages: int = 10,
    ):
        """Initialize the middleware.

        Args:
            project: The NovelProject instance
            max_context_tokens: Maximum context tokens before compression
            preserve_recent_messages: Number of recent messages to preserve during compression
        """
        super().__init__()
        self.project = project
        self.max_context_tokens = max_context_tokens
        self.preserve_recent_messages = preserve_recent_messages

        # Initialize memory store
        init_memory_store(project.path)

    def _build_auto_context(self) -> str:
        """Build the automatic context injection.

        This includes:
        - Project metadata
        - Current progress
        - Character states (from project state)
        - Memory summary (from agent memory)
        """
        config = self.project.config
        state = self.project.state

        parts = []

        # Project metadata
        world_display = config.world_type if config.world_type != "unset" else "未指定"
        parts.append(f"""【项目信息】
- 小说: 《{config.title}》
- 世界观: {world_display}
- 项目路径: {self.project.path}""")

        # Progress
        parts.append(f"""
【创作进度】
- 大纲: {state.outline_completed}/{state.outline_total or '?'} 章
- 正文: {state.writing_completed}/{state.writing_total or '?'} 章
- 当前章节: 第 {state.current_chapter} 章""")

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

        # Instructions for using memory tools
        parts.append("""
【记忆工具】
- remember(category, key, content): 记住信息 | recall(): 回忆 | forget(): 删除 | update_memory(): 追加
- 类别: character(角色), plot(剧情), foreshadow(伏笔), setting(设定), decision(决策), summary(摘要)

【角色工具】(专用，自动同步到项目状态)
- update_character(name, status?, location?, power_level?, note?): 更新角色
- get_character(name): 获取角色详情
- list_characters(status_filter?): 列出角色 | add_relationship(): 添加关系

【伏笔工具】
- plant_foreshadow(name, content, chapter?, target_chapter?): 埋伏笔
- resolve_foreshadow(name, resolved_chapter?, resolution?): 回收伏笔
- list_foreshadows(include_resolved?): 查看伏笔

【章节完成工具】(推荐，自动保存+更新进度+记录记忆)
- complete_chapter(chapter, content, summary, title?): 完成正文
- complete_outline(chapter, outline, title?): 完成大纲

【进度工具】
- get_progress(): 查看进度 | update_progress(): 手动更新

【工作流程】
1. 写新章节前: get_progress() + list_foreshadows() + list_characters()
2. 角色变化: update_character("索隆", status="已收服", note="第5章收服")
3. 埋伏笔: plant_foreshadow("神秘信件", "暗示身世")
4. 完成章节: complete_chapter(5, 正文, 摘要, "标题")
5. 回收伏笔: resolve_foreshadow("神秘信件", resolution="揭示真相")
""")

        return "\n".join(parts)

    def _get_modified_request(self, request: ModelRequest) -> ModelRequest:
        """Inject auto context into system prompt."""
        auto_context = self._build_auto_context()

        new_system_message = append_to_system_message(
            request.system_message,
            auto_context
        )

        return request.override(system_message=new_system_message)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject context and handle the request."""
        modified_request = self._get_modified_request(request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject context and handle the request."""
        modified_request = self._get_modified_request(request)
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
]
