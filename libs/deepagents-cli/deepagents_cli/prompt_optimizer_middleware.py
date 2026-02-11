"""Middleware for automatically optimizing user prompts using prompt-optimizer skill.

触发机制:
1. 显式标记模式（推荐）：用户在消息开头添加 @优化 或 @opt 标记
   示例: "@优化 帮我写个海贼王同人小说"
2. 关键词触发模式（可选）：检测消息中的关键词自动触发
3. 全局模式（可选）：对所有消息都触发优化

默认只启用显式标记模式，避免不必要的优化干扰。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import Overwrite

# 触发优化的显式标记（推荐方式）
OPTIMIZATION_MARKERS = [
    "@优化",
    "@opt",
    "@optimize",
    "/优化",
    "/opt",
]

# 触发优化的关键词（仅在 auto_optimize=True 时生效）
OPTIMIZATION_TRIGGER_KEYWORDS = [
    "小说",
    "网文",
    "故事",
    "创作",
    "写作",
    "同人",
    "novel",
    "story",
    "fiction",
]


class PromptOptimizerMiddleware(AgentMiddleware):
    """Middleware that optimizes user prompts using prompt-optimizer skill.

    触发方式:
    1. 显式标记（默认启用）: 用户在消息开头使用 @优化、@opt 等标记
       示例: "@优化 帮我写个海贼王同人小说"
    2. 关键词触发（默认禁用）: 检测消息中的小说/创作等关键词
    3. 全局触发（默认禁用）: 对所有消息都触发优化

    This middleware:
    1. Detects if the latest user message should be optimized
    2. Injects instructions to use prompt-optimizer skill before processing
    3. Ensures the optimized prompt is used for subsequent operations (like write_todos)
    """

    def __init__(
        self,
        auto_optimize: bool = False,  # 改为默认关闭关键词触发
        skill_name: str = "prompt-optimizer",
        always_optimize: bool = False,
        marker_mode: bool = True,  # 新增：显式标记模式（默认开启）
    ):
        """Initialize the PromptOptimizerMiddleware.

        Args:
            auto_optimize: If True, automatically optimize prompts containing trigger keywords.
                          If False, only optimize when explicitly requested. Default: False.
            skill_name: Name of the prompt-optimizer skill to use.
            always_optimize: If True, always optimize every user input (ignores trigger keywords).
                          If False, uses trigger keywords or explicit requests. Default: False.
            marker_mode: If True, only optimize when user uses explicit markers like @优化.
                        This is the recommended mode. Default: True.
        """
        super().__init__()
        self.auto_optimize = auto_optimize
        self.skill_name = skill_name
        self.always_optimize = always_optimize
        self.marker_mode = marker_mode

    def _has_optimization_marker(self, user_message: str) -> bool:
        """Check if user message starts with an optimization marker.

        Args:
            user_message: The user's message content.

        Returns:
            True if the message has an optimization marker, False otherwise.
        """
        message_lower = user_message.lower().strip()
        return any(message_lower.startswith(marker.lower()) for marker in OPTIMIZATION_MARKERS)

    def _remove_marker(self, user_message: str) -> str:
        """Remove the optimization marker from the message.

        Args:
            user_message: The user's message content.

        Returns:
            Message with marker removed.
        """
        message_stripped = user_message.strip()
        message_lower = message_stripped.lower()

        for marker in OPTIMIZATION_MARKERS:
            if message_lower.startswith(marker.lower()):
                # 移除标记和后面的空格
                return message_stripped[len(marker) :].lstrip()

        return user_message

    def _should_optimize(self, user_message: str) -> bool:
        """Determine if the user message should be optimized.

        Args:
            user_message: The user's message content.

        Returns:
            True if the message should be optimized, False otherwise.
        """
        if not user_message:
            return False

        # 如果启用了 always_optimize，总是优化（除非消息为空）
        if self.always_optimize:
            return True

        # 显式标记模式（推荐）：检查是否有优化标记
        if self.marker_mode and self._has_optimization_marker(user_message):
            return True

        # 如果只启用标记模式，不检查关键词
        if self.marker_mode and not self.auto_optimize:
            return False

        # 如果启用了自动优化，检查是否包含触发关键词
        if self.auto_optimize:
            return any(
                keyword.lower() in user_message.lower() for keyword in OPTIMIZATION_TRIGGER_KEYWORDS
            )

        return False

    def _get_latest_user_message(self, state: AgentState) -> str:
        """Extract the latest user message from state.

        Args:
            state: The agent state.

        Returns:
            The latest user message content, or empty string if not found.
        """
        messages = state.get("messages", [])
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

    def before_agent(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, any] | None:
        """Inject optimization instructions before agent execution.

        Args:
            state: Current agent state.
            runtime: Runtime context.

        Returns:
            State update with optimization instructions if needed, or None.
        """
        user_message = self._get_latest_user_message(state)

        # 检查是否应该优化
        if not self._should_optimize(user_message):
            return None

        # 如果使用标记模式，移除标记以获取实际要优化的内容
        if self.marker_mode and self._has_optimization_marker(user_message):
            user_message = self._remove_marker(user_message)

        # 检查是否已经优化过（避免重复优化）
        messages = state.get("messages", [])
        if messages:
            # 检查是否已经有优化指令或优化结果
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    content = msg.content
                    if isinstance(content, str):
                        # 如果已经包含优化指令或优化结果，跳过
                        if "prompt-optimizer" in content.lower() or "优化后的提示词" in content:
                            return None
                # 检查是否有 AI 消息包含优化结果
                if hasattr(msg, "type") and msg.type == "ai":
                    content = getattr(msg, "content", "")
                    if isinstance(content, str) and "优化后的提示词" in content:
                        return None

        # 创建优化指令系统消息
        # 职责：只负责触发优化，不管理后续流程
        # 技能选择由 agent 根据优化后的提示词内容自主决定，参考技能列表中的描述
        optimization_instruction = f"""## ⚠️ 重要：必须先优化提示词

**在开始任何操作（包括 write_todos）之前，你必须先优化用户的提示词。**

### 第一步：读取 prompt-optimizer 技能
1. 读取 `/skills/{self.skill_name}/SKILL.md` 了解优化方法
2. 从技能列表中确认技能的正确路径

### 第二步：优化提示词并流式输出
1. 分析用户原始提示词的问题（目标模糊、角色不清、上下文缺失等）
2. 按照技能中的步骤生成优化后的提示词
3. **必须流式输出优化后的提示词**，使用以下格式：
   ```
   ## 📝 优化后的提示词
   
   [在这里流式输出完整的优化后的提示词内容]
   ```
   注意：必须完整输出优化后的提示词，让用户能够看到优化结果

### 第三步：使用优化后的提示词
**重要：** 优化完成后，必须使用优化后的提示词（而不是原始提示词）来执行后续任务：
- 查看技能列表，根据优化后的提示词内容选择合适的技能
- 或使用优化后的提示词创建 todo 列表（write_todos）
- 或直接执行相应操作

**关键原则：**
- 始终使用优化后的提示词，而不是原始提示词
- 根据优化后的提示词内容，自主分析并选择合适的技能或工具
- 参考技能列表中的技能描述，选择最匹配的技能

**用户原始提示词：**
```
{user_message}
```

**你的任务：**
1. 先找到并读取 {self.skill_name} 技能
2. 优化这个提示词
3. **立即流式输出优化后的完整提示词**（使用 Markdown 格式，包含标题"## 📝 优化后的提示词"）
4. 根据优化后的提示词内容，选择合适的技能或工具来执行任务
5. 不要直接使用原始提示词进行后续操作

**重要：优化后的提示词必须完整输出到控制台，让用户能够看到完整的优化结果。**
"""

        # 在消息列表开头添加优化指令
        new_messages = [
            SystemMessage(content=optimization_instruction),
            *messages,
        ]

        return {"messages": Overwrite(new_messages)}

    async def abefore_agent(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, any] | None:
        """Async version of before_agent.

        Args:
            state: Current agent state.
            runtime: Runtime context.

        Returns:
            State update with optimization instructions if needed, or None.
        """
        return self.before_agent(state, runtime)


__all__ = ["PromptOptimizerMiddleware"]
