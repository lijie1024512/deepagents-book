"""Novel project management.

This module handles novel project creation, loading, and state management.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# Project directory structure
PROJECT_STRUCTURE = {
    ".novel": {
        "config.yaml": None,
        "state.yaml": None,
        "checkpoints": {},
        "logs": {},
    },
    "world": {
        "knowledge-base.md": None,
        "characters": {},
    },
    "outline": {
        "story-framework.md": None,
    },
    "chapters": {},
    "output": {},
}


@dataclass
class CharacterState:
    """Character current state."""

    name: str
    location: str = "未知"
    status: str = "未出场"  # 已收服/敌对/中立/未出场
    power_level: str = "未知"
    relationships: dict[str, str] = field(default_factory=dict)
    last_appearance: int = 0


@dataclass
class NovelState:
    """Novel project state."""

    # Progress
    outline_total: int = 0
    outline_completed: int = 0
    writing_total: int = 0
    writing_completed: int = 0
    current_chapter: int = 1

    # Characters
    characters: dict[str, CharacterState] = field(default_factory=dict)

    # Foreshadowing tracking
    foreshadowing: list[dict[str, Any]] = field(default_factory=list)

    # Butterfly effects
    butterfly_effects: list[dict[str, Any]] = field(default_factory=list)

    # Writing context
    last_chapter_summary: str = ""
    active_conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "progress": {
                "outline": {"total": self.outline_total, "completed": self.outline_completed},
                "writing": {
                    "total": self.writing_total,
                    "completed": self.writing_completed,
                    "current": self.current_chapter,
                },
            },
            "characters": {name: vars(char) for name, char in self.characters.items()},
            "foreshadowing": self.foreshadowing,
            "butterfly_effects": self.butterfly_effects,
            "context": {
                "last_chapter_summary": self.last_chapter_summary,
                "active_conflicts": self.active_conflicts,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> NovelState:
        """Create from dictionary."""
        state = cls()
        if "progress" in data:
            progress = data["progress"]
            if "outline" in progress:
                state.outline_total = progress["outline"].get("total", 0)
                state.outline_completed = progress["outline"].get("completed", 0)
            if "writing" in progress:
                state.writing_total = progress["writing"].get("total", 0)
                state.writing_completed = progress["writing"].get("completed", 0)
                state.current_chapter = progress["writing"].get("current", 1)

        if "characters" in data:
            for name, char_data in data["characters"].items():
                state.characters[name] = CharacterState(**char_data)

        if "foreshadowing" in data:
            state.foreshadowing = data["foreshadowing"]

        if "butterfly_effects" in data:
            state.butterfly_effects = data["butterfly_effects"]

        if "context" in data:
            ctx = data["context"]
            state.last_chapter_summary = ctx.get("last_chapter_summary", "")
            state.active_conflicts = ctx.get("active_conflicts", [])

        return state


@dataclass
class NovelConfig:
    """Novel project configuration."""

    title: str
    world_type: str = "original"  # onepiece/naruto/original
    created_at: str = ""
    author: str = ""
    description: str = ""

    # Model settings
    outline_model: str = "claude-sonnet-4-5-20250929"
    writing_model: str = "claude-sonnet-4-5-20250929"

    # Writing settings
    chapter_word_count: tuple[int, int] = (3000, 8000)
    auto_summary: bool = True
    progressive_mode: bool = True  # 渐进式场景确认

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "title": self.title,
            "world_type": self.world_type,
            "created_at": self.created_at,
            "author": self.author,
            "description": self.description,
            "models": {
                "outline": self.outline_model,
                "writing": self.writing_model,
            },
            "settings": {
                "chapter_word_count": list(self.chapter_word_count),
                "auto_summary": self.auto_summary,
                "progressive_mode": self.progressive_mode,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> NovelConfig:
        """Create from dictionary."""
        config = cls(
            title=data.get("title", "未命名"),
            world_type=data.get("world_type", "original"),
            created_at=data.get("created_at", ""),
            author=data.get("author", ""),
            description=data.get("description", ""),
        )
        if "models" in data:
            config.outline_model = data["models"].get("outline", config.outline_model)
            config.writing_model = data["models"].get("writing", config.writing_model)
        if "settings" in data:
            settings = data["settings"]
            if "chapter_word_count" in settings:
                config.chapter_word_count = tuple(settings["chapter_word_count"])
            config.auto_summary = settings.get("auto_summary", True)
            config.progressive_mode = settings.get("progressive_mode", True)
        return config


class NovelProject:
    """Novel project manager."""

    def __init__(self, path: Path):
        self.path = path
        self.config_file = path / ".novel" / "config.yaml"
        self.state_file = path / ".novel" / "state.yaml"
        self._config: NovelConfig | None = None
        self._state: NovelState | None = None

    @property
    def config(self) -> NovelConfig:
        """Get project configuration."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def state(self) -> NovelState:
        """Get project state."""
        if self._state is None:
            self._state = self._load_state()
        return self._state

    @property
    def exists(self) -> bool:
        """Check if project exists."""
        return self.config_file.exists()

    def _load_config(self) -> NovelConfig:
        """Load project configuration."""
        if self.config_file.exists():
            data = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
            return NovelConfig.from_dict(data)
        return NovelConfig(title="未命名")

    def _load_state(self) -> NovelState:
        """Load project state."""
        if self.state_file.exists():
            data = yaml.safe_load(self.state_file.read_text(encoding="utf-8"))
            return NovelState.from_dict(data)
        return NovelState()

    def save_config(self):
        """Save project configuration."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.dump(self.config.to_dict(), f, allow_unicode=True, default_flow_style=False)

    def save_state(self):
        """Save project state."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            yaml.dump(self.state.to_dict(), f, allow_unicode=True, default_flow_style=False)

        # Create checkpoint
        self._create_checkpoint()

    def _create_checkpoint(self):
        """Create a state checkpoint."""
        checkpoint_dir = self.path / ".novel" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        chapter = self.state.current_chapter
        checkpoint_file = checkpoint_dir / f"{timestamp}-chapter-{chapter}.yaml"

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            yaml.dump(self.state.to_dict(), f, allow_unicode=True, default_flow_style=False)

    @classmethod
    def create(cls, path: Path, title: str, world_type: str = "original") -> NovelProject:
        """Create a new novel project."""
        project = cls(path)

        # Create directory structure
        _create_directory_structure(path, PROJECT_STRUCTURE)

        # Initialize config
        project._config = NovelConfig(
            title=title,
            world_type=world_type,
            created_at=datetime.now().isoformat(),
        )
        project.save_config()

        # Initialize state
        project._state = NovelState()
        project.save_state()

        # Create initial files
        _create_initial_files(path, title, world_type)

        return project

    @classmethod
    def load(cls, path: Path) -> NovelProject:
        """Load an existing project."""
        project = cls(path)
        if not project.exists:
            raise FileNotFoundError(f"No novel project found at {path}")
        return project

    @classmethod
    def find_project(cls, start_path: Path | None = None) -> NovelProject | None:
        """Find a novel project in the current or parent directories."""
        if start_path is None:
            start_path = Path.cwd()

        current = start_path.resolve()

        while current != current.parent:
            config_file = current / ".novel" / "config.yaml"
            if config_file.exists():
                return cls(current)
            current = current.parent

        return None

    def get_chapter_outline(self, chapter: int) -> str:
        """Get outline for a specific chapter."""
        # Try to find the chapter outline file
        volume = (chapter - 1) // 50 + 1  # Assuming 50 chapters per volume
        outline_file = self.path / "outline" / f"volume-{volume}" / f"chapter-{chapter:03d}.md"

        if outline_file.exists():
            return outline_file.read_text(encoding="utf-8")

        # Fallback to main outline file
        main_outline = self.path / "outline" / "story-framework.md"
        if main_outline.exists():
            return main_outline.read_text(encoding="utf-8")

        return ""

    def get_chapter_content(self, chapter: int) -> str:
        """Get content of a written chapter."""
        volume = (chapter - 1) // 50 + 1
        chapter_file = self.path / "chapters" / f"volume-{volume}" / f"chapter-{chapter:03d}.md"

        if chapter_file.exists():
            return chapter_file.read_text(encoding="utf-8")
        return ""

    def get_chapter_summary(self, chapter: int) -> str:
        """Get summary of a written chapter."""
        volume = (chapter - 1) // 50 + 1
        summary_file = self.path / "chapters" / f"volume-{volume}" / f"chapter-{chapter:03d}.summary.md"

        if summary_file.exists():
            return summary_file.read_text(encoding="utf-8")
        return ""

    def save_chapter(self, chapter: int, content: str):
        """Save chapter content."""
        volume = (chapter - 1) // 50 + 1
        chapter_dir = self.path / "chapters" / f"volume-{volume}"
        chapter_dir.mkdir(parents=True, exist_ok=True)

        chapter_file = chapter_dir / f"chapter-{chapter:03d}.md"
        chapter_file.write_text(content, encoding="utf-8")

    def save_chapter_summary(self, chapter: int, summary: str):
        """Save chapter summary."""
        volume = (chapter - 1) // 50 + 1
        chapter_dir = self.path / "chapters" / f"volume-{volume}"
        chapter_dir.mkdir(parents=True, exist_ok=True)

        summary_file = chapter_dir / f"chapter-{chapter:03d}.summary.md"
        summary_file.write_text(summary, encoding="utf-8")

    def get_context_for_writing(self, chapter: int) -> str:
        """Build context for writing a chapter."""
        context_parts = []

        # 1. Project state
        context_parts.append(self._format_project_state())

        # 2. Chapter outline
        outline = self.get_chapter_outline(chapter)
        if outline:
            context_parts.append(f"## 第{chapter}章大纲\n\n{outline}")

        # 3. Previous chapter summary
        if chapter > 1:
            summary = self.get_chapter_summary(chapter - 1)
            if summary:
                context_parts.append(f"## 上一章（第{chapter - 1}章）摘要\n\n{summary}")

        # 4. Active foreshadowing
        pending = [f for f in self.state.foreshadowing if not f.get("resolved", False)]
        if pending:
            foreshadow_text = "\n".join([f"- 第{f['chapter']}章: {f['content']}" for f in pending])
            context_parts.append(f"## 待回收伏笔\n\n{foreshadow_text}")

        return "\n\n---\n\n".join(context_parts)

    def _format_project_state(self) -> str:
        """Format project state as context."""
        lines = [
            f"## 项目状态",
            f"",
            f"**小说**: {self.config.title}",
            f"**世界观**: {self.config.world_type}",
            f"**进度**: 大纲 {self.state.outline_completed}/{self.state.outline_total} 章，"
            f"正文 {self.state.writing_completed}/{self.state.writing_total} 章",
            f"**当前章节**: 第 {self.state.current_chapter} 章",
            f"",
        ]

        # Character states
        if self.state.characters:
            lines.append("### 主要角色状态")
            lines.append("")
            for name, char in self.state.characters.items():
                lines.append(f"- **{name}**: {char.status}，位置：{char.location}")
            lines.append("")

        return "\n".join(lines)


def _create_directory_structure(base: Path, structure: dict):
    """Recursively create directory structure."""
    for name, content in structure.items():
        path = base / name
        if content is None:
            # It's a file placeholder, don't create
            pass
        elif isinstance(content, dict):
            path.mkdir(parents=True, exist_ok=True)
            _create_directory_structure(path, content)
        else:
            path.mkdir(parents=True, exist_ok=True)


def _create_initial_files(path: Path, title: str, world_type: str):
    """Create initial project files."""
    # Story framework
    framework_file = path / "outline" / "story-framework.md"
    framework_file.write_text(
        f"""# {title} - 故事框架

## 基本信息

- **小说名称**: {title}
- **世界观**: {world_type}
- **创建时间**: {datetime.now().strftime("%Y-%m-%d")}

## 主角设定

（待填写）

## 故事梗概

（待填写）

## 核心冲突

（待填写）

## 卷结构规划

### 第一卷

（待填写）
""",
        encoding="utf-8",
    )

    # Knowledge base placeholder
    kb_file = path / "world" / "knowledge-base.md"
    kb_file.write_text(
        f"""# {title} - 世界观知识库

## 世界观类型: {world_type}

（根据世界观类型，这里会加载对应的知识库内容）
""",
        encoding="utf-8",
    )


def list_projects(base_dir: Path | None = None) -> list[NovelProject]:
    """List all novel projects in the base directory."""
    if base_dir is None:
        # Default to ~/novels
        base_dir = Path.home() / "novels"

    if not base_dir.exists():
        return []

    projects = []
    for item in base_dir.iterdir():
        if item.is_dir():
            config_file = item / ".novel" / "config.yaml"
            if config_file.exists():
                projects.append(NovelProject(item))

    return projects
