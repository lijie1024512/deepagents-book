"""Imitate Memory Middleware.

Simplified context injection for the agent-driven novel imitation workflow:
1. Loads orchestrator Skill (always) + generation guide Skill
2. Injects project metadata and available tools reference
3. No phase tracking — the agent decides its own workflow

Follows the same pattern as NovelMemoryMiddleware.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)

from deepagents_cli.novel.imitate_tools import (
    _get_db,
    init_imitate_store,
)

if TYPE_CHECKING:
    from deepagents_cli.novel.project import NovelProject

logger = logging.getLogger(__name__)


class ImitateMemoryMiddleware(AgentMiddleware):
    """Middleware for the novel imitation workflow.

    Injects Skill content and project context into each model call.
    """

    def __init__(self, project: NovelProject):
        """Initialize the middleware.

        Args:
            project: The NovelProject instance (mode=imitate).
        """
        super().__init__()
        self.project = project
        self._skill_cache: dict[str, str] = {}

        init_imitate_store(project.path)

    def _load_skill_file(self, skill_name: str) -> str:
        """Load a SKILL.md file by skill name, with caching.

        Args:
            skill_name: e.g. "novel-imitate-orchestrator"

        Returns:
            Content of the SKILL.md file, or empty string if not found.
        """
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]

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

    def _build_auto_context(self) -> str:
        """Build context to inject into the system prompt."""
        parts: list[str] = []

        # Project metadata
        config = self.project.config
        parts.append(
            f"【仿写项目信息】\n"
            f"- 小说: 《{config.title}》\n"
            f"- 模式: 仿写\n"
            f"- 项目路径: {self.project.path}"
        )

        # Quick status: saved analyses + generated chapters
        db = _get_db()
        if db is not None:
            with db._connection() as conn:
                analysis_keys = conn.execute(
                    "SELECT key FROM imitate_analysis ORDER BY key"
                ).fetchall()
                chapter_count = conn.execute("SELECT COUNT(*) FROM imitate_chapters").fetchone()[0]
            if analysis_keys:
                keys_str = ", ".join(k[0] for k in analysis_keys)
                parts.append(f"【已保存分析】{keys_str}")
            if chapter_count:
                parts.append(f"【已生成章节】{chapter_count} 章")

        # Load orchestrator skill (always)
        orchestrator = self._load_skill_file("novel-imitate-orchestrator")
        if orchestrator:
            parts.append(f"\n{orchestrator}")

        # Load generation guide skill
        generation = self._load_skill_file("novel-imitate-generation")
        if generation:
            parts.append(f"\n{generation}")

        # Tool quick reference
        parts.append(
            "【仿写工具速查】\n"
            "- 索引: index_source\n"
            "- 阅读: read_source_chapter / read_source_range / search_source\n"
            "- 分析: save_analysis / get_analysis\n"
            "- 生成: get_generation_context / save_chapter\n"
            "- 状态: get_project_status"
        )

        return "\n".join(parts)

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
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject context and handle the request."""
        modified_request = self._get_modified_request(request)
        return await handler(modified_request)


__all__ = ["ImitateMemoryMiddleware"]
