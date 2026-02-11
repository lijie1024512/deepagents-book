"""Tests for novel source file chunking and indexing module."""

import pytest

from deepagents_cli.novel.chunker import (
    ChapterInfo,
    SourceIndex,
    chunk_source_novel,
    detect_encoding,
    get_chunk_sample_indices,
    index_source_novel,
    load_chapter_range_text,
    load_chapter_text,
    load_chunk_text,
    scan_chapter_boundaries,
    search_source_text,
)


@pytest.fixture
def utf8_novel(tmp_path):
    """Create a small UTF-8 novel file with chapter markers."""
    content = """第一章 初入江湖

张三走在路上，心中百感交集。他刚刚离开了家乡，踏上了修仙之路。

路边的花草树木都显得格外陌生，但他并不害怕。

第二章 奇遇

他在山中遇到了一位老人，老人给了他一本古书。

"这是修炼的秘笈，好好学习。"老人说完就消失了。

第三章 修炼

张三按照古书的指引，开始了漫长的修炼之路。

每天清晨，他都会在山顶打坐冥想。

第四章 出关

经过三个月的修炼，张三终于突破了第一重境界。

他决定下山，去看看外面的世界。
"""
    f = tmp_path / "novel.txt"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def no_chapter_novel(tmp_path):
    """Create a novel file without chapter markers."""
    content = "这是一段很长的文字。\n" * 500
    f = tmp_path / "plain.txt"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def english_novel(tmp_path):
    """Create an English novel file with chapter markers."""
    content = """Chapter 1

It was a dark and stormy night. The wind howled through the trees.

Chapter 2

The next morning was calm and peaceful. Birds sang in the branches.

Chapter 3

By afternoon, the adventure had truly begun.
"""
    f = tmp_path / "english.txt"
    f.write_text(content, encoding="utf-8")
    return f


class TestDetectEncoding:
    """Test encoding detection."""

    def test_detect_encoding_utf8(self, utf8_novel):
        """UTF-8 files should be detected correctly."""
        assert detect_encoding(utf8_novel) == "utf-8"

    def test_detect_encoding_ascii(self, tmp_path):
        """ASCII files should be detected as UTF-8 (superset)."""
        f = tmp_path / "ascii.txt"
        f.write_text("hello world\n", encoding="ascii")
        assert detect_encoding(f) == "utf-8"

    def test_detect_encoding_gbk(self, tmp_path):
        """GBK-encoded files should be detected."""
        f = tmp_path / "gbk.txt"
        # Write content that is valid GBK but not valid UTF-8
        content = "这是测试内容"
        f.write_bytes(content.encode("gbk"))
        enc = detect_encoding(f)
        assert enc in ("gbk", "gb2312", "gb18030")


class TestScanChapterBoundaries:
    """Test chapter boundary detection."""

    def test_scan_chinese_chapters(self, utf8_novel):
        """Should detect Chinese chapter markers (第X章)."""
        boundaries = scan_chapter_boundaries(utf8_novel)
        assert len(boundaries) == 4

    def test_scan_english_chapters(self, english_novel):
        """Should detect English chapter markers (Chapter N)."""
        boundaries = scan_chapter_boundaries(english_novel)
        assert len(boundaries) == 3

    def test_scan_no_chapters(self, no_chapter_novel):
        """Files without chapter markers should return empty list."""
        boundaries = scan_chapter_boundaries(no_chapter_novel)
        assert len(boundaries) == 0

    def test_scan_chinese_numeral_variants(self, tmp_path):
        """Should detect various Chinese numeral formats."""
        content = "第一章 开始\n内容\n第二十三章 继续\n内容\n第100章 结尾\n"
        f = tmp_path / "variants.txt"
        f.write_text(content, encoding="utf-8")
        boundaries = scan_chapter_boundaries(f)
        assert len(boundaries) == 3


class TestIndexSourceNovel:
    """Test chapter-based indexing."""

    def test_index_chinese_novel(self, utf8_novel):
        """Should build correct index for Chinese novel."""
        index = index_source_novel(utf8_novel)
        assert isinstance(index, SourceIndex)
        assert index.encoding == "utf-8"
        assert index.total_chars > 0
        assert len(index.chapters) == 4
        assert index.chapters[0].chapter_id == 1
        assert "初入江湖" in index.chapters[0].title

    def test_index_english_novel(self, english_novel):
        """Should build correct index for English novel."""
        index = index_source_novel(english_novel)
        assert len(index.chapters) == 3
        assert index.chapters[0].chapter_id == 1
        assert "Chapter 1" in index.chapters[0].title

    def test_index_no_chapters(self, no_chapter_novel):
        """Novel without chapters should have empty chapter list."""
        index = index_source_novel(no_chapter_novel)
        assert len(index.chapters) == 0
        assert index.total_chars > 0

    def test_chapter_ids_sequential(self, utf8_novel):
        """Chapter IDs should be sequential starting from 1."""
        index = index_source_novel(utf8_novel)
        for i, ch in enumerate(index.chapters):
            assert ch.chapter_id == i + 1

    def test_chapter_info_fields(self, utf8_novel):
        """ChapterInfo should have all required fields."""
        index = index_source_novel(utf8_novel)
        ch = index.chapters[0]
        assert isinstance(ch, ChapterInfo)
        assert ch.char_count > 0
        assert ch.byte_count > 0
        assert ch.char_offset >= 0
        assert ch.byte_offset >= 0


class TestLoadChapterText:
    """Test chapter text loading."""

    def test_load_first_chapter(self, utf8_novel):
        """Should load correct text for first chapter."""
        index = index_source_novel(utf8_novel)
        text = load_chapter_text(utf8_novel, index, 1)
        assert "初入江湖" in text
        assert "张三走在路上" in text

    def test_load_specific_chapter(self, utf8_novel):
        """Should load correct text for a specific chapter."""
        index = index_source_novel(utf8_novel)
        text = load_chapter_text(utf8_novel, index, 3)
        assert "修炼" in text
        assert "打坐冥想" in text

    def test_load_invalid_chapter_raises(self, utf8_novel):
        """Should raise ValueError for non-existent chapter."""
        index = index_source_novel(utf8_novel)
        with pytest.raises(ValueError, match="not found"):
            load_chapter_text(utf8_novel, index, 99)

    def test_chapters_dont_overlap(self, utf8_novel):
        """Each chapter's text should be distinct."""
        index = index_source_novel(utf8_novel)
        ch1 = load_chapter_text(utf8_novel, index, 1)
        ch2 = load_chapter_text(utf8_novel, index, 2)
        # Chapter 2 content should not appear in chapter 1
        assert "古书" not in ch1
        assert "张三走在路上" not in ch2


class TestLoadChapterRangeText:
    """Test chapter range loading."""

    def test_load_range(self, utf8_novel):
        """Should load multiple chapters."""
        index = index_source_novel(utf8_novel)
        text = load_chapter_range_text(utf8_novel, index, 1, 3)
        assert "初入江湖" in text
        assert "古书" in text
        assert "打坐冥想" in text

    def test_load_single_chapter_range(self, utf8_novel):
        """Range with start==end should load one chapter."""
        index = index_source_novel(utf8_novel)
        text = load_chapter_range_text(utf8_novel, index, 2, 2)
        assert "古书" in text

    def test_invalid_range_raises(self, utf8_novel):
        """Invalid ranges should raise ValueError."""
        index = index_source_novel(utf8_novel)
        with pytest.raises(ValueError, match="Invalid chapter range"):
            load_chapter_range_text(utf8_novel, index, 3, 1)


class TestSearchSourceText:
    """Test keyword search."""

    def test_search_existing_keyword(self, utf8_novel):
        """Should find existing keywords."""
        results = search_source_text(utf8_novel, "utf-8", "张三")
        assert len(results) > 0
        for _offset, snippet in results:
            assert "张三" in snippet

    def test_search_nonexistent_keyword(self, utf8_novel):
        """Should return empty for non-existent keyword."""
        results = search_source_text(utf8_novel, "utf-8", "不存在的关键词xyz")
        assert len(results) == 0

    def test_search_max_results(self, utf8_novel):
        """Should respect max_results limit."""
        results = search_source_text(utf8_novel, "utf-8", "张三", max_results=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# Legacy chunking functions (backward compatibility)
# ---------------------------------------------------------------------------
class TestChunkSourceNovel:
    """Test intelligent chunking."""

    def test_chunk_small_file(self, utf8_novel):
        """Small files should produce minimal chunks."""
        result = chunk_source_novel(utf8_novel, chunk_size=100000)
        assert result.total_chars > 0
        assert result.total_chapters == 4
        assert len(result.chunks) >= 1
        assert result.encoding == "utf-8"

    def test_chunk_respects_chapters(self, utf8_novel):
        """Chunks should align with chapter boundaries when possible."""
        result = chunk_source_novel(utf8_novel, chunk_size=100)
        assert result.total_chapters == 4
        chapter_chunks = [c for c in result.chunks if c.chapter_range is not None]
        assert len(chapter_chunks) > 0

    def test_chunk_no_chapters_fallback(self, no_chapter_novel):
        """Without chapter markers, should use fixed-size chunking."""
        result = chunk_source_novel(no_chapter_novel, chunk_size=1000, overlap_size=100)
        assert result.total_chapters == 0
        assert len(result.chunks) > 1
        for c in result.chunks:
            assert c.chapter_range is None

    def test_chunk_covers_full_text(self, utf8_novel):
        """Chunks should cover the entire file content."""
        result = chunk_source_novel(utf8_novel, chunk_size=100000)
        total_chunk_chars = sum(c.char_count for c in result.chunks)
        assert total_chunk_chars <= result.total_chars + 100

    def test_chunk_ids_sequential(self, utf8_novel):
        """Chunk IDs should be sequential starting from 0."""
        result = chunk_source_novel(utf8_novel, chunk_size=100)
        for i, c in enumerate(result.chunks):
            assert c.chunk_id == i


class TestLoadChunkText:
    """Test lazy chunk loading."""

    def test_load_chunk_text_correctness(self, utf8_novel):
        """Loaded text should match the original content at the given offsets."""
        result = chunk_source_novel(utf8_novel, chunk_size=100000)
        full_text = utf8_novel.read_text(encoding="utf-8")

        for chunk in result.chunks:
            loaded = load_chunk_text(utf8_novel, chunk, result.encoding)
            assert len(loaded) > 0
            assert loaded in full_text

    def test_load_specific_chunk(self, utf8_novel):
        """Should load the correct chunk by its byte offsets."""
        result = chunk_source_novel(utf8_novel, chunk_size=100)
        if len(result.chunks) > 1:
            chunk0 = load_chunk_text(utf8_novel, result.chunks[0], result.encoding)
            chunk1 = load_chunk_text(utf8_novel, result.chunks[1], result.encoding)
            assert chunk0 != chunk1


class TestGetChunkSampleIndices:
    """Test sampling strategy for large files."""

    def test_small_total_returns_all(self):
        """When total <= max_samples, return all indices."""
        indices = get_chunk_sample_indices(10, max_samples=25)
        assert indices == list(range(10))

    def test_exact_max_returns_all(self):
        """When total == max_samples, return all indices."""
        indices = get_chunk_sample_indices(25, max_samples=25)
        assert indices == list(range(25))

    def test_large_total_respects_max(self):
        """When total > max_samples, should not exceed max_samples."""
        indices = get_chunk_sample_indices(100, max_samples=25)
        assert len(indices) <= 25

    def test_includes_first_and_last(self):
        """Should always include the first 3 and last 2 chunks."""
        indices = get_chunk_sample_indices(100, max_samples=10)
        assert 0 in indices
        assert 1 in indices
        assert 2 in indices
        assert 99 in indices
        assert 98 in indices

    def test_sorted_output(self):
        """Output should be sorted."""
        indices = get_chunk_sample_indices(50, max_samples=10)
        assert indices == sorted(indices)

    def test_single_chunk(self):
        """Edge case: single chunk."""
        indices = get_chunk_sample_indices(1, max_samples=25)
        assert indices == [0]
