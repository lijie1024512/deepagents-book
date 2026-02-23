"""Imitate Memory Middleware.

State-aware context injection for the agent-driven novel imitation workflow:
1. Detects project state (planning vs generation) from database
2. Planning phase: injects orchestrator Skill (DNA analysis, creative proposals)
3. Generation phase: injects generation guide Skill ONLY (focused writing instructions)
4. Never injects both simultaneously — avoids attention dilution

Follows the same pattern as NovelMemoryMiddleware.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone, timedelta
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
        self._prompt_call_count = 0

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

    def _load_skill_references(self, skill_content: str) -> str:
        """Load inject_references from a skill's frontmatter.

        Adapted from NovelMemoryMiddleware._load_phase_references().

        Args:
            skill_content: The full SKILL.md content with YAML frontmatter

        Returns:
            Concatenated reference file contents, or empty string.
        """
        refs = self._parse_inject_references(skill_content)
        if not refs:
            return ""

        skills_dir = Path(__file__).parent.parent / "skills"
        parts: list[str] = []
        for ref in refs:
            for skill_dir in skills_dir.iterdir():
                ref_path = skill_dir / ref
                if ref_path.exists():
                    with contextlib.suppress(OSError):
                        parts.append(ref_path.read_text(encoding="utf-8"))
                    break

        return "\n\n".join(parts)

    @staticmethod
    def _parse_inject_references(skill_content: str) -> list[str]:
        """Parse inject_references list from SKILL.md YAML frontmatter."""
        if not skill_content.startswith("---"):
            return []

        try:
            end_idx = skill_content.index("---", 3)
        except ValueError:
            return []
        frontmatter = skill_content[3:end_idx]

        refs: list[str] = []
        in_refs = False
        for line in frontmatter.split("\n"):
            stripped = line.strip()
            if stripped.startswith("inject_references:"):
                val = stripped[len("inject_references:"):].strip()
                if val == "[]":
                    return []
                in_refs = True
                continue
            if in_refs:
                if stripped.startswith("- "):
                    refs.append(stripped[2:].strip())
                elif not stripped.startswith("#") and stripped:
                    in_refs = False
        return refs

    def _detect_phase(self) -> str:
        """Detect current project phase from database state.

        Returns:
            "planning" if no adaptation_plan exists yet,
            "generation" if adaptation_plan + character_mapping exist.
        """
        db = _get_db()
        if db is None:
            return "planning"

        with db._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM imitate_analysis WHERE key='adaptation_plan'"
            ).fetchone()

        return "generation" if row else "planning"

    def _build_auto_context(self) -> str:
        """Build context to inject into the system prompt.

        State-aware injection:
        - Planning phase: inject orchestrator SKILL (DNA analysis, proposals)
        - Generation phase: inject generation SKILL ONLY (writing instructions)
        Never both simultaneously — prevents attention dilution.
        """
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
        analysis_keys_list: list[str] = []
        chapter_count = 0
        if db is not None:
            with db._connection() as conn:
                analysis_keys = conn.execute(
                    "SELECT key FROM imitate_analysis ORDER BY key"
                ).fetchall()
                chapter_count = conn.execute("SELECT COUNT(*) FROM imitate_chapters").fetchone()[0]
            analysis_keys_list = [k[0] for k in analysis_keys]
            if analysis_keys_list:
                parts.append(f"【已保存分析】{', '.join(analysis_keys_list)}")
            if chapter_count:
                parts.append(f"【已生成章节】{chapter_count} 章")

        # --- State-aware SKILL injection ---
        phase = self._detect_phase()

        if phase == "planning":
            # Planning: inject orchestrator + generation guide
            orchestrator = self._load_skill_file("novel-imitate-orchestrator")
            if orchestrator:
                parts.append(f"\n{orchestrator}")
                # Load reference files (golden finger patterns etc.)
                refs = self._load_skill_references(orchestrator)
                if refs:
                    parts.append(f"\n{refs}")
            generation = self._load_skill_file("novel-imitate-generation")
            if generation:
                parts.append(f"\n{generation}")
            # Full tool reference for planning
            parts.append(
                "【仿写工具速查】\n"
                "- 索引: index_source\n"
                "- 阅读: read_source_range（批量读多章）/ read_source_chapter（单章精读）/ search_source\n"
                "- 分析: save_analysis / get_analysis\n"
                "- 生成: get_generation_context / save_chapter\n"
                "- 状态: get_project_status\n\n"
                "【⚠️ 工具调用效率规则】\n"
                "- 读多章时用 read_source_range(1, 3) 一次读取，禁止对每章分别调用 read_source_chapter\n"
                "- write_todos 整个分析流程最多调1次（开头规划时），不要每步都更新\n"
                "- 尽量合并工具调用，减少不必要的轮次"
            )
        else:
            # Generation: ONLY inject generation guide — keep context focused
            generation = self._load_skill_file("novel-imitate-generation")
            if generation:
                parts.append(f"\n{generation}")
            # Streamlined tool reference for generation
            parts.append(
                "【章节生成工具流程（严格遵循！）】\n"
                "每章只需3步：\n"
                "1. read_source_chapter(chapter=N) → 精读源文，学习写作技法（描写密度/文风/人物刻画）\n"
                "2. get_generation_context(chapter=N) → 获取改编计划+角色映射+金手指+氛围DNA+前文摘要\n"
                "3. 结合技法+改编计划，原创写作 → save_chapter(chapter=N, content=..., summary=..., title=...)\n\n"
                "⚠️ save_chapter 必须一次性提供 content 和 summary，不要分两次调用！\n"
                "⚠️ save_chapter 之后直接向用户汇报完成情况，不要再调用任何工具！\n\n"
                "【⚠️ 正文格式要求】\n"
                "- 正文必须是纯文本，禁止使用任何Markdown格式符号\n"
                "- 不要使用 **粗体**、*斜体*、# 标题、- 列表等Markdown语法\n"
                "- 对话使用中文引号（""），段落之间用空行分隔\n"
                "- 不要在content中包含章节标题（save_chapter会自动生成）\n\n"
                "【⚠️ 仿写核心原则】\n"
                "- 学源文的'怎么写'（技法），不抄源文的'写了什么'（内容）\n"
                "- 质量优于原文：源文N个描写维度，你要N+1个维度\n"
                "- 不要换名抄袭：不能把源文句子换个人名就用\n\n"
                "【严禁以下操作】\n"
                "- 不要调用 ls、index_source、get_analysis、read_file\n"
                "- 不要在 save_chapter 之后调用任何工具（remember、write_todos等全部禁止）\n"
                "- get_generation_context 已包含所有必要信息，不需要额外获取"
            )

        return "\n".join(parts)

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


__all__ = ["ImitateMemoryMiddleware"]
