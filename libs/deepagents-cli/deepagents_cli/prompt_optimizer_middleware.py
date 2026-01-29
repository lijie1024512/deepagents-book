"""Middleware for automatically optimizing user prompts using prompt-optimizer skill."""

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

# 触发优化的关键词（如果用户输入包含这些词，自动触发优化）
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
    """Middleware that automatically optimizes user prompts using prompt-optimizer skill.

    This middleware:
    1. Detects if the latest user message should be optimized
    2. Injects instructions to use prompt-optimizer skill before processing
    3. Ensures the optimized prompt is used for subsequent operations (like write_todos)
    """

    def __init__(self, auto_optimize: bool = True, skill_name: str = "prompt-optimizer", always_optimize: bool = False):
        """Initialize the PromptOptimizerMiddleware.

        Args:
            auto_optimize: If True, automatically optimize prompts containing trigger keywords.
                          If False, only optimize when explicitly requested.
            skill_name: Name of the prompt-optimizer skill to use.
            always_optimize: If True, always optimize every user input (ignores trigger keywords).
                          If False, uses trigger keywords or explicit requests.
        """
        super().__init__()
        self.auto_optimize = auto_optimize
        self.skill_name = skill_name
        self.always_optimize = always_optimize

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

        # 如果用户明确要求优化，总是优化
        if any(keyword in user_message.lower() for keyword in ["优化", "改进", "optimize", "improve"]):
            return True

        # 如果启用了自动优化，检查是否包含触发关键词
        if self.auto_optimize:
            return any(
                keyword.lower() in user_message.lower()
                for keyword in OPTIMIZATION_TRIGGER_KEYWORDS
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

