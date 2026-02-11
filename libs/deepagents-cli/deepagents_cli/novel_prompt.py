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

# 当小说工具可用时注入的工具使用说明
NOVEL_TOOL_INSTRUCTIONS = """
## 小说项目工具

**重要**: 当用户想要创建新小说时，**必须**使用 `init_novel_project` 工具来创建完整的项目结构，
**绝对不要**直接用 `write_file` 创建一个单独的 .md 文件来代替完整项目。

### 可用工具
- `init_novel_project(title, world_type?, directory?)`: 创建完整的小说项目结构
  - world_type 可选值: `onepiece`(海贼王), `naruto`(火影), `bleach`(死神), `original`(原创，默认)
  - 会自动创建: .novel/(配置+数据库), world/(世界观), outline/(大纲), chapters/(正文), output/(导出)
- `get_project_status()`: 获取当前项目的完整状态报告（进度、角色、伏笔等）

### 创建新小说的正确流程
1. 和用户确认小说标题和世界观类型
2. 使用 `init_novel_project(title, world_type)` 创建完整项目结构
3. 然后在对话中引导用户规划角色、世界观和大纲
4. 将规划内容保存到项目对应的目录中（outline/、world/ 等）

### 注意事项
- 如果用户说"新建小说"、"写一本新小说"、"创建一个小说项目"等，先用 `init_novel_project` 创建项目
- 不要先去浏览已有文件或目录，直接和用户确认需求后创建
- 创建完项目后，提示用户可以使用 `deepagents novel start` 进入完整创作模式
"""


class NovelPromptMiddleware(AgentMiddleware):
    """Middleware for injecting novel writing prompt when user input is novel-related.

    This middleware:
    1. Detects if the latest user message contains novel-related keywords
    2. Loads the novel writing prompt from systemPromt.md if detected
    3. Injects the prompt into the system message
    4. Optionally injects tool usage instructions when novel tools are available
    """

    def __init__(
        self,
        prompt_file_path: Path | str | None = None,
        *,
        include_tool_instructions: bool = False,
    ) -> None:
        """Initialize the NovelPromptMiddleware.

        Args:
            prompt_file_path: Path to the novel prompt file. If None, uses default path.
            include_tool_instructions: If True, append novel tool usage instructions
                when novel-related content is detected. Should be True when
                init_novel_project tool is available in the agent's tool set.
        """
        super().__init__()
        if prompt_file_path is None:
            # 默认路径：libs/deepagents-cli/deepagents_cli/prompts/systemPromt.md
            default_path = Path(__file__).parent / "prompts" / "systemPromt.md"
            self.prompt_file_path = default_path
        else:
            self.prompt_file_path = Path(prompt_file_path)

        self._cached_prompt: str | None = None
        self._include_tool_instructions = include_tool_instructions

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

        # Append tool instructions if novel tools are available
        full_prompt = novel_prompt
        if self._include_tool_instructions:
            full_prompt += "\n\n" + NOVEL_TOOL_INSTRUCTIONS

        # 将小说提示词追加到系统消息中
        new_system_message = append_to_system_message(request.system_message, full_prompt)

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
