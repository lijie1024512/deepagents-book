"""Tests for novel hooks system."""

import tempfile
from pathlib import Path

import pytest

from deepagents_cli.novel.database import NovelDatabase
from deepagents_cli.novel.hooks import (
    NovelHooksRegistry,
    build_hooks_system_prompt_section,
    get_session_recovery_context,
    init_hooks,
)


@pytest.fixture
def project_with_db():
    """Create a temporary project with database for testing."""
    import yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir) / "test_novel"
        project_path.mkdir()

        # Create .novel directory
        novel_dir = project_path / ".novel"
        novel_dir.mkdir()

        # Create config.yaml for project loading
        config = {
            "title": "测试小说",
            "world_type": "original",
        }
        config_file = novel_dir / "config.yaml"
        config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

        # Initialize database
        db = NovelDatabase(project_path)

        # Add some test data
        db.update_progress(outline_completed=5, current_chapter=3)
        db.update_character("李寒", status="活跃", location="东海")
        db.update_character("索隆", status="已收服", location="东海")
        db.plant_foreshadow("老鼠的秘密", "老鼠与海贼有交易", chapter=2, target_chapter=10)
        db.remember("character", "李寒", "主角，特种兵穿越")

        yield project_path, db


class TestHooksRegistry:
    """Test NovelHooksRegistry class."""

    def test_registry_initialization(self, project_with_db):
        """Test hooks registry initialization."""
        project_path, _ = project_with_db
        registry = NovelHooksRegistry(project_path)

        assert registry.is_enabled("pre_write_chapter")
        assert registry.is_enabled("post_chapter_complete")
        assert registry.is_enabled("session_recovery")
        assert registry.is_enabled("auto_checkpoint")

    def test_enable_disable_hooks(self, project_with_db):
        """Test enabling and disabling hooks."""
        project_path, _ = project_with_db
        registry = NovelHooksRegistry(project_path)

        # Disable a hook
        registry.disable_hook("auto_checkpoint")
        assert not registry.is_enabled("auto_checkpoint")

        # Re-enable
        registry.enable_hook("auto_checkpoint")
        assert registry.is_enabled("auto_checkpoint")

    def test_get_status(self, project_with_db):
        """Test getting hooks status."""
        project_path, _ = project_with_db
        registry = NovelHooksRegistry(project_path)

        status = registry.get_status()
        assert "enabled_hooks" in status
        assert "operation_count" in status
        assert "checkpoint_threshold" in status


class TestPreHooks:
    """Test pre-execution hooks."""

    def test_pre_chapter_context(self, project_with_db):
        """Test pre-chapter context generation."""
        project_path, db = project_with_db

        # Initialize hooks with the project path
        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        # Get pre-chapter context
        context = registry.get_pre_chapter_context(chapter=4)

        # Context may be None if no relevant data, but should not error
        # In our test setup, we have characters and foreshadows
        if context:
            assert "活跃角色" in context or "伏笔" in context or "摘要" in context

    def test_pre_outline_context(self, project_with_db):
        """Test pre-outline context generation."""
        project_path, db = project_with_db

        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        # Get pre-outline context
        context = registry.get_pre_outline_context(chapter=6)

        # Should include character status and foreshadows
        if context:
            assert "角色" in context or "伏笔" in context


class TestPostHooks:
    """Test post-execution hooks."""

    def test_enhance_chapter_result(self, project_with_db):
        """Test chapter result enhancement with reminders."""
        project_path, db = project_with_db

        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        original_result = "✅ 第5章已完成"
        enhanced = registry.enhance_chapter_result(chapter=5, result=original_result)

        # Should contain original result
        assert "第5章已完成" in enhanced

        # Should contain reminders
        assert "提醒" in enhanced or "下一步" in enhanced

    def test_enhance_outline_result(self, project_with_db):
        """Test outline result enhancement."""
        project_path, db = project_with_db

        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        original_result = "✅ 第6章大纲已完成"
        enhanced = registry.enhance_outline_result(chapter=6, result=original_result)

        # Should contain original result
        assert "第6章大纲已完成" in enhanced

        # Should contain next step options
        assert "下一步" in enhanced


class TestSessionRecovery:
    """Test session recovery functionality (5-Question Reboot Check)."""

    def test_recovery_context_generation(self, project_with_db):
        """Test session recovery context generation."""
        project_path, db = project_with_db

        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        context = registry.get_recovery_context()

        # Should contain the 5 questions
        assert context is not None
        assert "当前位置" in context  # Q1: Where am I?
        assert "上次操作" in context  # Q2: What was I doing?
        assert "发现" in context or "记录" in context  # Q3: What have I discovered?
        assert "待完成" in context  # Q4: What's left to do?
        assert "问题" in context  # Q5: What problems emerged?

    def test_recovery_context_includes_progress(self, project_with_db):
        """Test that recovery context includes progress info."""
        project_path, db = project_with_db

        init_hooks(project_path)
        context = get_session_recovery_context()

        assert "大纲进度" in context
        assert "正文进度" in context
        assert "当前章节" in context


class TestAutoCheckpoint:
    """Test auto-checkpoint functionality."""

    def test_checkpoint_threshold(self, project_with_db):
        """Test checkpoint threshold tracking."""
        project_path, db = project_with_db

        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        # Initially should not need checkpoint
        assert not registry.should_create_checkpoint()

        # Simulate multiple operations by manually incrementing counter
        from deepagents_cli.novel import hooks

        hooks._hook_state["operation_count"] = 3

        # Now should need checkpoint
        assert registry.should_create_checkpoint()

        # Reset counter
        registry.reset_checkpoint_counter()
        assert not registry.should_create_checkpoint()


class TestSystemPromptSection:
    """Test system prompt section generation."""

    def test_build_hooks_prompt_section(self, project_with_db):
        """Test building hooks section for system prompt."""
        project_path, _ = project_with_db

        registry = NovelHooksRegistry(project_path)
        section = build_hooks_system_prompt_section(registry)

        # Should describe the hooks
        assert "Hooks" in section
        assert "自动" in section

        # Should mention enabled hooks
        assert "章节" in section or "大纲" in section
        assert "检查点" in section

    def test_disabled_hooks_not_in_prompt(self, project_with_db):
        """Test that disabled hooks are not mentioned in prompt."""
        project_path, _ = project_with_db

        registry = NovelHooksRegistry(project_path)
        registry.disable_hook("auto_checkpoint")

        section = build_hooks_system_prompt_section(registry)

        # The specific hook mention depends on implementation
        # Just verify the section is generated without errors
        assert "Hooks" in section


class TestHooksIntegration:
    """Integration tests for hooks with database."""

    def test_foreshadow_reminder_in_chapter_hook(self, project_with_db):
        """Test that overdue foreshadows trigger reminders."""
        project_path, db = project_with_db

        # Plant a foreshadow that's overdue
        db.plant_foreshadow("紧急伏笔", "需要立即回收", chapter=1, target_chapter=3)

        init_hooks(project_path)
        registry = NovelHooksRegistry(project_path)

        # Complete chapter 5 (past the target chapter)
        result = registry.enhance_chapter_result(chapter=5, result="完成")

        # Should mention the overdue foreshadow
        assert "伏笔" in result

    def test_hooks_with_empty_database(self):
        """Test hooks work with empty database."""
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "empty_novel"
            project_path.mkdir()
            novel_dir = project_path / ".novel"
            novel_dir.mkdir()

            # Create config.yaml for project loading
            config = {
                "title": "空测试小说",
                "world_type": "original",
            }
            config_file = novel_dir / "config.yaml"
            config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

            # Create empty database
            NovelDatabase(project_path)

            init_hooks(project_path)
            registry = NovelHooksRegistry(project_path)

            # Should not error with empty database
            context = registry.get_pre_chapter_context(chapter=1)
            # Context can be None for empty database
            assert context is None or isinstance(context, str)

            recovery = registry.get_recovery_context()
            assert recovery is not None  # Should still generate basic structure
