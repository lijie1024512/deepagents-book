"""Middleware for injecting novel writing prompt into system prompt when relevant."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import HumanMessage

from deepagents.middleware._utils import append_to_system_message

# 小说相关关键词，用于检测用户输入是否与小说创作相关
NOVEL_KEYWORDS = [
    "小说",
    "网文",
    "故事",
    "情节",
    "人物",
    "角色",
    "世界观",
    "大纲",
    "开篇",
    "章节",
    "剧情",
    "主角",
    "配角",
    "反派",
    "金手指",
    "爽点",
    "泪点",
    "悬念",
    "创作",
    "写作",
    "网文小说",
    "网络小说",
    "novel",
    "story",
    "plot",
    "character",
]


class NovelPromptMiddleware(AgentMiddleware):
    """Middleware for injecting novel writing prompt when user input is novel-related.

    This middleware:
    1. Detects if the latest user message contains novel-related keywords
    2. Loads the novel writing prompt from systemPromt.md if detected
    3. Injects the prompt into the system message
    """

    def __init__(self, prompt_file_path: Path | str | None = None):
        """Initialize the NovelPromptMiddleware.

        Args:
            prompt_file_path: Path to the novel prompt file. If None, uses default path.
        """
        super().__init__()
        if prompt_file_path is None:
            # 默认路径：libs/deepagents-cli/deepagents_cli/prompts/systemPromt.md
            default_path = Path(__file__).parent / "prompts" / "systemPromt.md"
            self.prompt_file_path = default_path
        else:
            self.prompt_file_path = Path(prompt_file_path)
        
        self._cached_prompt: str | None = None

    def _load_novel_prompt(self) -> str:
        """Load the novel writing prompt from file.

        Returns:
            The prompt content as a string, or empty string if file not found.
        """
        # 使用缓存避免重复读取
        if self._cached_prompt is not None:
            return self._cached_prompt
        
        try:
            if self.prompt_file_path.exists():
                self._cached_prompt = self.prompt_file_path.read_text(encoding="utf-8")
                return self._cached_prompt
        except Exception:
            # 如果读取失败，返回空字符串
            pass
        
        return ""

    def _is_novel_related(self, text: str) -> bool:
        """Check if the text is related to novel writing.

        Args:
            text: The text to check.

        Returns:
            True if the text contains novel-related keywords, False otherwise.
        """
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in NOVEL_KEYWORDS)

    def _get_latest_user_message(self, request: ModelRequest) -> str:
        """Extract the latest user message from the request.

        Args:
            request: The model request.

        Returns:
            The latest user message content, or empty string if not found.
        """
        # 从 request.state 中获取消息列表
        messages = request.state.get("messages", [])
        if messages:
            # 从后往前查找最新的用户消息
            for message in reversed(messages):
                if isinstance(message, HumanMessage):
                    content = message.content
                    if isinstance(content, str):
                        return content
                    elif isinstance(content, list):
                        # 处理多模态内容
                        text_parts = [
                            item.get("text", "") if isinstance(item, dict) else str(item)
                            for item in content
                        ]
                        return " ".join(text_parts)
        
        return ""

    def _should_inject_prompt(self, request: ModelRequest) -> bool:
        """Determine if the novel prompt should be injected.

        Args:
            request: The model request.

        Returns:
            True if the prompt should be injected, False otherwise.
        """
        user_message = self._get_latest_user_message(request)
        return self._is_novel_related(user_message)

    def _get_modified_request(self, request: ModelRequest) -> ModelRequest | None:
        """Get modified request with novel prompt injected, or None if not needed.

        Args:
            request: The original model request.

        Returns:
            Modified request with novel prompt appended, or None if not needed.
        """
        if not self._should_inject_prompt(request):
            return None

        novel_prompt = self._load_novel_prompt()
        if not novel_prompt:
            return None

        # 将小说提示词追加到系统消息中
        new_system_message = append_to_system_message(
            request.system_message, novel_prompt
        )

        return request.override(system_message=new_system_message)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject novel prompt into system prompt when relevant.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        modified_request = self._get_modified_request(request)
        return handler(modified_request if modified_request else request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject novel prompt into system prompt when relevant.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        modified_request = self._get_modified_request(request)
        return await handler(modified_request if modified_request else request)


__all__ = ["NovelPromptMiddleware"]

