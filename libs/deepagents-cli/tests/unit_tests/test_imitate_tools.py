"""Tests for novel imitation tools module (simplified 9-tool API)."""

import pytest

from deepagents_cli.novel.database import NovelDatabase
from deepagents_cli.novel.imitate_tools import (
    _get_db,
    get_analysis,
    get_generation_context,
    get_project_status,
    index_source,
    read_source_chapter,
    read_source_range,
    save_analysis,
    save_chapter,
    search_source,
    setup_imitate_project,
)


@pytest.fixture
def imitate_project(tmp_path):
    """Create a temporary imitation project with a source file."""
    project_path = tmp_path / "test_imitate"
    project_path.mkdir()
    (project_path / ".novel").mkdir()

    # Create a source novel file
    source_file = tmp_path / "source_novel.txt"
    content = """第一章 开始

这是第一章的内容。主角张三出场了。他走在街上，心中百感交集。

第二章 冒险

张三开始了他的冒险旅程。他遇到了一位神秘老人。
老人给了他一本古书，说："这是你命中注定的机缘。"

第三章 修炼

张三获得了金手指，开始修炼。每天清晨他都在山顶打坐冥想。
"""
    source_file.write_text(content, encoding="utf-8")

    # Create NovelDatabase first (initializes base schema)
    NovelDatabase(project_path)

    # Setup imitate project
    setup_imitate_project(project_path, source_file, "测试仿写")

    return project_path


class TestImitateSchemaCreation:
    """Test database schema creation."""

    def test_schema_creates_all_tables(self, imitate_project):
        """All imitate tables should be created."""
        db = NovelDatabase(imitate_project)
        with db._connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'imitate_%'"
            ).fetchall()
        table_names = {t[0] for t in tables}
        expected = {
            "imitate_source",
            "imitate_analysis",
            "imitate_chapters",
        }
        assert expected.issubset(table_names)

    def test_source_metadata_saved(self, imitate_project):
        """Source file metadata should be saved."""
        db = _get_db()
        assert db is not None
        with db._connection() as conn:
            row = conn.execute(
                "SELECT file_path, file_size FROM imitate_source WHERE id=1"
            ).fetchone()
        assert row is not None
        assert "source_novel.txt" in row[0]
        assert row[1] > 0

    def test_source_file_copied(self, imitate_project):
        """Source file should be copied to source/ directory."""
        source_copy = imitate_project / "source" / "source_novel.txt"
        assert source_copy.exists()
        text = source_copy.read_text(encoding="utf-8")
        assert "张三" in text

    def test_directories_created(self, imitate_project):
        """All project subdirectories should be created."""
        for subdir in ("source", "analysis", "chapters", "output"):
            assert (imitate_project / subdir).is_dir()


class TestIndexSourceTool:
    """Test index_source tool."""

    def test_index_returns_table_of_contents(self, imitate_project):
        """index_source should return chapter listing."""
        result = index_source.invoke({})
        assert "索引完成" in result
        assert "编码" in result
        assert "第一章" in result or "开始" in result

    def test_index_updates_database(self, imitate_project):
        """index_source should save metadata to database."""
        index_source.invoke({})
        db = _get_db()
        assert db is not None
        with db._connection() as conn:
            row = conn.execute(
                "SELECT total_chars, total_chapters FROM imitate_source WHERE id=1"
            ).fetchone()
        assert row is not None
        assert row[0] > 0  # total_chars
        assert row[1] > 0  # total_chapters


class TestReadSourceChapterTool:
    """Test read_source_chapter tool."""

    def test_read_first_chapter(self, imitate_project):
        """Should read the first chapter text."""
        index_source.invoke({})
        result = read_source_chapter.invoke({"chapter": 1})
        assert "张三" in result
        assert "第一章" in result or "开始" in result

    def test_read_invalid_chapter(self, imitate_project):
        """Should return error for non-existent chapter."""
        index_source.invoke({})
        result = read_source_chapter.invoke({"chapter": 99})
        assert "错误" in result

    def test_read_without_index(self, imitate_project):
        """Should prompt to index first."""
        # Reset module state to force re-init without index
        import deepagents_cli.novel.imitate_tools as mod

        mod._source_index = None
        # read_source_chapter should still work (it calls _get_source_index internally)
        result = read_source_chapter.invoke({"chapter": 1})
        # Either works or returns meaningful error
        assert "张三" in result or "错误" in result


class TestReadSourceRangeTool:
    """Test read_source_range tool."""

    def test_read_range(self, imitate_project):
        """Should read multiple chapters."""
        index_source.invoke({})
        result = read_source_range.invoke({"start_chapter": 1, "end_chapter": 2})
        assert "张三" in result
        assert "古书" in result or "冒险" in result

    def test_invalid_range(self, imitate_project):
        """Should return error for invalid range."""
        index_source.invoke({})
        result = read_source_range.invoke({"start_chapter": 3, "end_chapter": 1})
        assert "错误" in result


class TestSearchSourceTool:
    """Test search_source tool."""

    def test_search_found(self, imitate_project):
        """Should find existing keywords."""
        index_source.invoke({})
        result = search_source.invoke({"keyword": "张三"})
        assert "张三" in result
        assert "匹配" in result

    def test_search_not_found(self, imitate_project):
        """Should indicate when keyword not found."""
        index_source.invoke({})
        result = search_source.invoke({"keyword": "不存在的角色xyz"})
        assert "未找到" in result


class TestSaveAndGetAnalysis:
    """Test analysis key-value store."""

    def test_save_and_retrieve(self, imitate_project):
        """Should save and retrieve analysis by key."""
        save_result = save_analysis.invoke(
            {
                "key": "dna_analysis",
                "content": "## 文风DNA\n短句为主，节奏紧凑。",
            }
        )
        assert "保存成功" in save_result

        get_result = get_analysis.invoke({"key": "dna_analysis"})
        assert "短句为主" in get_result

    def test_get_nonexistent_key(self, imitate_project):
        """Should return helpful message for missing key."""
        result = get_analysis.invoke({"key": "nonexistent"})
        assert "未找到" in result

    def test_overwrite_key(self, imitate_project):
        """Should allow overwriting existing key."""
        save_analysis.invoke({"key": "test_key", "content": "版本1"})
        save_analysis.invoke({"key": "test_key", "content": "版本2"})
        result = get_analysis.invoke({"key": "test_key"})
        assert "版本2" in result
        assert "版本1" not in result

    def test_exports_to_file(self, imitate_project):
        """Should export analysis to analysis/ directory."""
        save_analysis.invoke(
            {
                "key": "character_mapping",
                "content": "张三→李逍遥",
            }
        )
        export_file = imitate_project / "analysis" / "character_mapping.md"
        assert export_file.exists()
        text = export_file.read_text(encoding="utf-8")
        assert "李逍遥" in text

    def test_list_available_keys(self, imitate_project):
        """Should list available keys when key not found."""
        save_analysis.invoke({"key": "key_a", "content": "a"})
        save_analysis.invoke({"key": "key_b", "content": "b"})
        result = get_analysis.invoke({"key": "nonexistent"})
        assert "key_a" in result
        assert "key_b" in result


class TestSaveChapterTool:
    """Test save_chapter tool."""

    def test_save_chapter(self, imitate_project):
        """Should save generated chapter."""
        result = save_chapter.invoke(
            {
                "chapter": 1,
                "content": "第一章正文内容...",
                "summary": "李逍遥初入江湖",
                "title": "初入江湖",
            }
        )
        assert "保存成功" in result

    def test_chapter_file_created(self, imitate_project):
        """Should create chapter file on disk."""
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": "正文内容",
                "summary": "摘要",
                "title": "标题",
            }
        )
        chapter_file = imitate_project / "chapters" / "chapter-001.md"
        assert chapter_file.exists()
        text = chapter_file.read_text(encoding="utf-8")
        assert "正文内容" in text
        assert "标题" in text

    def test_save_multiple_chapters(self, imitate_project):
        """Should track chapter count."""
        save_chapter.invoke({"chapter": 1, "content": "ch1", "summary": "s1"})
        result = save_chapter.invoke({"chapter": 2, "content": "ch2", "summary": "s2"})
        assert "2" in result  # should show 2 chapters generated


class TestGetGenerationContext:
    """Test get_generation_context tool."""

    def test_context_includes_source_text(self, imitate_project):
        """Should include source chapter text as style reference."""
        index_source.invoke({})
        result = get_generation_context.invoke({"chapter": 1})
        assert "风格参考" in result or "源小说" in result
        assert "张三" in result

    def test_context_includes_previous_summaries(self, imitate_project):
        """Should include summaries of previously generated chapters."""
        index_source.invoke({})
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": "第一章正文",
                "summary": "李逍遥出场了",
                "title": "出场",
            }
        )
        result = get_generation_context.invoke({"chapter": 2})
        assert "李逍遥出场了" in result

    def test_context_includes_analysis(self, imitate_project):
        """Should include saved analysis data."""
        index_source.invoke({})
        save_analysis.invoke(
            {
                "key": "character_mapping",
                "content": "张三→李逍遥",
            }
        )
        result = get_generation_context.invoke({"chapter": 1})
        assert "李逍遥" in result


class TestGetProjectStatus:
    """Test get_project_status tool."""

    def test_status_initial(self, imitate_project):
        """Should return status for a fresh project."""
        result = get_project_status.invoke({})
        assert "仿写项目状态" in result
        assert "source_novel.txt" in result

    def test_status_after_index(self, imitate_project):
        """Should show source info after indexing."""
        index_source.invoke({})
        result = get_project_status.invoke({})
        assert "章节数" in result

    def test_status_after_analysis(self, imitate_project):
        """Should show saved analyses."""
        save_analysis.invoke({"key": "test_key", "content": "test"})
        result = get_project_status.invoke({})
        assert "test_key" in result

    def test_status_after_chapters(self, imitate_project):
        """Should show generated chapters."""
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": "内容",
                "summary": "摘要",
                "title": "标题",
            }
        )
        result = get_project_status.invoke({})
        assert "1" in result
        assert "章" in result
