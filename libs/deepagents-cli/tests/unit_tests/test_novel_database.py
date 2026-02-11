"""Tests for novel SQLite database module."""

import tempfile
from pathlib import Path

import pytest

from deepagents_cli.novel.database import NovelDatabase


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir) / "test_novel"
        project_path.mkdir()
        yield NovelDatabase(project_path)


class TestProgress:
    """Test progress operations."""

    def test_initial_progress(self, db):
        """Test initial progress values."""
        progress = db.get_progress()
        assert progress["outline_total"] == 50
        assert progress["outline_completed"] == 0
        assert progress["current_chapter"] == 1

    def test_update_progress(self, db):
        """Test updating progress."""
        db.update_progress(outline_completed=10, current_chapter=5)
        progress = db.get_progress()
        assert progress["outline_completed"] == 10
        assert progress["current_chapter"] == 5


class TestCharacters:
    """Test character operations."""

    def test_create_character(self, db):
        """Test creating a character."""
        db.update_character("索隆", status="已收服", location="东海")
        char = db.get_character("索隆")
        assert char is not None
        assert char["status"] == "已收服"
        assert char["location"] == "东海"

    def test_update_character(self, db):
        """Test updating an existing character."""
        db.update_character("索隆", status="未收服")
        db.update_character("索隆", status="已收服", power_level="剑士")
        char = db.get_character("索隆")
        assert char["status"] == "已收服"
        assert char["power_level"] == "剑士"

    def test_list_characters(self, db):
        """Test listing characters."""
        db.update_character("索隆", status="已收服")
        db.update_character("娜美", status="未收服")
        db.update_character("路飞", status="已收服")

        all_chars = db.list_characters()
        assert len(all_chars) == 3

        recruited = db.list_characters(status_filter="已收服")
        assert len(recruited) == 2

    def test_add_relationship(self, db):
        """Test adding character relationships."""
        db.add_relationship("李寒", "索隆", "上下级", mutual=True)

        li_han = db.get_character("李寒")
        assert li_han["relationships"]["索隆"] == "上下级"

        zoro = db.get_character("索隆")
        assert zoro["relationships"]["李寒"] == "上下级"


class TestForeshadowing:
    """Test foreshadowing operations."""

    def test_plant_foreshadow(self, db):
        """Test planting a foreshadow."""
        db.plant_foreshadow("老鼠的秘密", "老鼠与海贼有交易", chapter=3, target_chapter=10)
        fs = db.get_foreshadow("老鼠的秘密")
        assert fs is not None
        assert fs["content"] == "老鼠与海贼有交易"
        assert fs["planted_chapter"] == 3
        assert fs["resolved"] == 0

    def test_resolve_foreshadow(self, db):
        """Test resolving a foreshadow."""
        db.plant_foreshadow("老鼠的秘密", "内容", chapter=3)
        db.resolve_foreshadow("老鼠的秘密", resolved_chapter=10, resolution="老鼠被捕")

        fs = db.get_foreshadow("老鼠的秘密")
        assert fs["resolved"] == 1
        assert fs["resolved_chapter"] == 10
        assert fs["resolution"] == "老鼠被捕"

    def test_list_foreshadows(self, db):
        """Test listing foreshadows."""
        db.plant_foreshadow("伏笔1", "内容1", chapter=1)
        db.plant_foreshadow("伏笔2", "内容2", chapter=2)
        db.plant_foreshadow("伏笔3", "内容3", chapter=3)
        db.resolve_foreshadow("伏笔2", resolved_chapter=5)

        pending = db.list_foreshadows(include_resolved=False)
        assert len(pending) == 2

        all_fs = db.list_foreshadows(include_resolved=True)
        assert len(all_fs) == 3


class TestMemory:
    """Test memory operations."""

    def test_remember_and_recall(self, db):
        """Test basic remember/recall."""
        db.remember("character", "索隆", "三刀流剑士")
        result = db.recall("character", "索隆")
        assert result["content"] == "三刀流剑士"

    def test_recall_category(self, db):
        """Test recalling all entries in a category."""
        db.remember("character", "索隆", "剑士")
        db.remember("character", "娜美", "航海士")

        chars = db.recall("character")
        assert "索隆" in chars
        assert "娜美" in chars

    def test_recall_all(self, db):
        """Test recalling all memory."""
        db.remember("character", "索隆", "剑士")
        db.remember("plot", "主线", "打败老鼠")

        all_memory = db.recall()
        assert "character" in all_memory
        assert "plot" in all_memory

    def test_forget(self, db):
        """Test forgetting memory."""
        db.remember("character", "索隆", "剑士")
        assert db.forget("character", "索隆")
        assert db.recall("character", "索隆") == {}


class TestCheckpoints:
    """Test checkpoint operations."""

    def test_create_checkpoint(self, db):
        """Test creating a checkpoint."""
        db.update_progress(current_chapter=5)
        db.update_character("索隆", status="已收服")

        checkpoint_id = db.create_checkpoint("第5章完成")
        assert checkpoint_id > 0

        checkpoints = db.list_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0]["name"] == "第5章完成"
        assert checkpoints[0]["checkpoint_type"] == "manual"

    def test_restore_checkpoint(self, db):
        """Test restoring from checkpoint."""
        # Initial state
        db.update_progress(current_chapter=5)
        db.update_character("索隆", status="已收服")
        checkpoint_id = db.create_checkpoint("test")

        # Modify state
        db.update_progress(current_chapter=10)
        db.update_character("索隆", status="离队")

        # Verify modified
        assert db.get_progress()["current_chapter"] == 10
        assert db.get_character("索隆")["status"] == "离队"

        # Restore
        assert db.restore_checkpoint(checkpoint_id)

        # Verify restored
        assert db.get_progress()["current_chapter"] == 5
        assert db.get_character("索隆")["status"] == "已收服"


class TestTransaction:
    """Test transaction handling."""

    def test_atomic_transaction(self, db):
        """Test atomic transaction."""
        with db.transaction() as conn:
            conn.execute("UPDATE progress SET current_chapter=10 WHERE id=1")
            conn.execute(
                "INSERT INTO characters (name, status) VALUES (?, ?)", ("测试角色", "测试")
            )

        assert db.get_progress()["current_chapter"] == 10
        assert db.get_character("测试角色") is not None

    def test_rollback_on_error(self, db):
        """Test rollback on error."""
        try:
            with db.transaction() as conn:
                conn.execute("UPDATE progress SET current_chapter=99 WHERE id=1")
                # This should fail - invalid SQL
                conn.execute("INVALID SQL STATEMENT")
        except Exception:
            pass

        # Progress should be unchanged due to rollback
        assert db.get_progress()["current_chapter"] == 1


class TestWALMode:
    """Test WAL mode is enabled."""

    def test_wal_mode_enabled(self, db):
        """Test that WAL mode is enabled for concurrent safety."""
        with db._connection() as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0].lower() == "wal"
