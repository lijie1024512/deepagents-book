"""Source novel file indexing and reading utilities.

Provides tools for the agent to flexibly access source novel content:
- Encoding detection (UTF-8/GBK/GB2312/BIG5)
- Chapter boundary scanning via regex
- Chapter-based indexing (chapter number -> byte offset mapping)
- Flexible text loading by chapter or byte offset
- Smart chunking for files without chapter markers
- Keyword search within source text
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Chapter heading patterns (Chinese + English)
_CHAPTER_PATTERNS = [
    # 第X章/节/卷/回 (Chinese numerals or digits)
    re.compile(r"^\s*第[一二三四五六七八九十百千零\d]+[章节卷回]"),
    # Chinese ordinal with separator: 一、 二、 三.
    re.compile(r"^\s*[一二三四五六七八九十百千]+[、.]"),
    # Chapter N / CHAPTER N
    re.compile(r"^\s*[Cc]hapter\s+\d+"),
    # Digit prefix: 1、 2. 3  (but not dates or random numbers)
    re.compile(r"^\s*\d{1,4}[、.\s]"),
]


@dataclass
class ChapterInfo:
    """Metadata for a single chapter in the source novel."""

    chapter_id: int
    title: str
    char_offset: int  # character offset in the full text
    byte_offset: int  # byte offset in the file
    char_count: int  # character count
    byte_count: int  # byte count


@dataclass
class SourceIndex:
    """Index of a source novel file."""

    file_path: Path
    encoding: str
    total_chars: int
    total_bytes: int
    chapters: list[ChapterInfo] = field(default_factory=list)


@dataclass
class ChunkInfo:
    """Metadata for a single chunk of source text (for non-chapter files)."""

    chunk_id: int
    start_offset: int  # byte offset
    end_offset: int  # byte offset (exclusive)
    char_count: int
    chapter_range: tuple[int, int] | None  # (start_chapter, end_chapter) or None


@dataclass
class ChunkingResult:
    """Result of chunking a source novel file."""

    total_chars: int
    total_chapters: int
    chunks: list[ChunkInfo]
    chapter_boundaries: list[int]  # character offset list
    encoding: str


def detect_encoding(file_path: Path) -> str:
    """Detect file encoding. Tries UTF-8 first, falls back to common Chinese encodings.

    Args:
        file_path: Path to the text file.

    Returns:
        Detected encoding string (e.g. "utf-8", "gbk").
    """
    raw = file_path.read_bytes()

    # Try UTF-8 first (most common for modern files)
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # Try common Chinese encodings
    for enc in ("gbk", "gb2312", "big5", "gb18030"):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback to chardet if available
    try:
        import chardet  # type: ignore[import-untyped]

        result = chardet.detect(raw[:100_000])
        if result and result.get("encoding"):
            return result["encoding"].lower()
    except ImportError:
        pass

    return "utf-8"  # ultimate fallback


def scan_chapter_boundaries(file_path: Path, encoding: str = "utf-8") -> list[int]:
    """Scan chapter boundaries in a text file.

    Returns character offsets where chapter headings are found.

    Args:
        file_path: Path to the source novel file.
        encoding: File encoding.

    Returns:
        Sorted list of character offsets for chapter boundaries.
    """
    text = file_path.read_text(encoding=encoding)
    boundaries: list[int] = []
    offset = 0

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            for pattern in _CHAPTER_PATTERNS:
                if pattern.match(stripped):
                    boundaries.append(offset)
                    break
        offset += len(line) + 1  # +1 for the newline

    return boundaries


def index_source_novel(file_path: Path) -> SourceIndex:
    """Build a chapter-based index of a source novel file.

    Scans the file for chapter boundaries, builds an index mapping
    each chapter to its byte/char offset, allowing the agent to
    read any chapter on demand.

    Args:
        file_path: Path to the source novel file.

    Returns:
        SourceIndex with chapter metadata.
    """
    encoding = detect_encoding(file_path)
    text = file_path.read_text(encoding=encoding)
    total_chars = len(text)
    total_bytes = file_path.stat().st_size

    boundaries = scan_chapter_boundaries(file_path, encoding)

    chapters: list[ChapterInfo] = []
    for i, char_off in enumerate(boundaries):
        # Extract title from the heading line
        line_end = text.find("\n", char_off)
        if line_end == -1:
            line_end = total_chars
        title = text[char_off:line_end].strip()

        # Calculate char count (until next chapter or EOF)
        next_off = boundaries[i + 1] if i + 1 < len(boundaries) else total_chars
        ch_chars = next_off - char_off

        # Calculate byte offsets
        byte_off = len(text[:char_off].encode(encoding))
        byte_end = len(text[:next_off].encode(encoding))

        chapters.append(
            ChapterInfo(
                chapter_id=i + 1,
                title=title,
                char_offset=char_off,
                byte_offset=byte_off,
                char_count=ch_chars,
                byte_count=byte_end - byte_off,
            )
        )

    return SourceIndex(
        file_path=file_path,
        encoding=encoding,
        total_chars=total_chars,
        total_bytes=total_bytes,
        chapters=chapters,
    )


def load_chapter_text(
    file_path: Path,
    index: SourceIndex,
    chapter_id: int,
) -> str:
    """Load text for a specific chapter by its ID.

    Args:
        file_path: Path to the source novel file.
        index: SourceIndex from index_source_novel().
        chapter_id: 1-based chapter ID.

    Returns:
        The text content of the chapter.

    Raises:
        ValueError: If chapter_id is out of range.
    """
    for ch in index.chapters:
        if ch.chapter_id == chapter_id:
            with file_path.open("rb") as f:
                f.seek(ch.byte_offset)
                raw = f.read(ch.byte_count)
            return raw.decode(index.encoding)

    msg = f"Chapter {chapter_id} not found. Valid range: 1-{len(index.chapters)}"
    raise ValueError(msg)


def load_chapter_range_text(
    file_path: Path,
    index: SourceIndex,
    start_chapter: int,
    end_chapter: int,
) -> str:
    """Load text for a range of chapters.

    Args:
        file_path: Path to the source novel file.
        index: SourceIndex from index_source_novel().
        start_chapter: 1-based start chapter ID (inclusive).
        end_chapter: 1-based end chapter ID (inclusive).

    Returns:
        The concatenated text of the chapters.

    Raises:
        ValueError: If chapter range is invalid.
    """
    if not index.chapters:
        msg = "No chapters found in the source index."
        raise ValueError(msg)

    max_id = max(ch.chapter_id for ch in index.chapters)
    if start_chapter < 1 or end_chapter > max_id or start_chapter > end_chapter:
        msg = f"Invalid chapter range {start_chapter}-{end_chapter}. Valid: 1-{max_id}"
        raise ValueError(msg)

    parts = []
    for ch in index.chapters:
        if start_chapter <= ch.chapter_id <= end_chapter:
            with file_path.open("rb") as f:
                f.seek(ch.byte_offset)
                raw = f.read(ch.byte_count)
            parts.append(raw.decode(index.encoding))

    return "".join(parts)


def search_source_text(
    file_path: Path,
    encoding: str,
    keyword: str,
    context_chars: int = 200,
    max_results: int = 10,
) -> list[tuple[int, str]]:
    """Search for a keyword in the source novel.

    Args:
        file_path: Path to the source novel file.
        encoding: File encoding.
        keyword: Keyword to search for.
        context_chars: Number of characters of context around each match.
        max_results: Maximum number of results to return.

    Returns:
        List of (char_offset, context_snippet) tuples.
    """
    text = file_path.read_text(encoding=encoding)
    results: list[tuple[int, str]] = []
    start = 0

    while len(results) < max_results:
        pos = text.find(keyword, start)
        if pos == -1:
            break

        # Extract context
        ctx_start = max(0, pos - context_chars)
        ctx_end = min(len(text), pos + len(keyword) + context_chars)
        snippet = text[ctx_start:ctx_end]

        # Add ellipsis markers
        if ctx_start > 0:
            snippet = "..." + snippet
        if ctx_end < len(text):
            snippet = snippet + "..."

        results.append((pos, snippet))
        start = pos + len(keyword)

    return results


# ---------------------------------------------------------------------------
# Legacy functions kept for backward compatibility with existing tests
# ---------------------------------------------------------------------------
def chunk_source_novel(
    file_path: Path,
    chunk_size: int = 50000,
    overlap_size: int = 2000,
    respect_chapters: bool = True,
) -> ChunkingResult:
    """Intelligently chunk a source novel file.

    Prefers splitting at chapter boundaries when available.
    Falls back to fixed-size + overlap splitting when no chapter markers exist.

    Args:
        file_path: Path to the source novel file.
        chunk_size: Target chunk size in characters.
        overlap_size: Overlap between chunks in characters (used in non-chapter mode).
        respect_chapters: Whether to try splitting at chapter boundaries.

    Returns:
        ChunkingResult with chunk metadata.
    """
    encoding = detect_encoding(file_path)
    text = file_path.read_text(encoding=encoding)
    total_chars = len(text)

    # Scan chapter boundaries
    boundaries = scan_chapter_boundaries(file_path, encoding) if respect_chapters else []
    total_chapters = len(boundaries)

    # Build char-to-byte offset mapping for boundary points
    def _char_to_byte_offset(char_offset: int) -> int:
        return len(text[:char_offset].encode(encoding))

    chunks: list[ChunkInfo] = []

    if boundaries and total_chapters >= 2:
        # Chapter-aware chunking: group chapters to fit within chunk_size
        chunk_id = 0
        group_start_idx = 0  # index into boundaries

        while group_start_idx < total_chapters:
            group_start_char = boundaries[group_start_idx]
            group_end_idx = group_start_idx

            # Greedily add chapters until chunk_size is exceeded
            while group_end_idx < total_chapters:
                # End of this group: start of next chapter, or end of file
                if group_end_idx + 1 < total_chapters:
                    tentative_end_char = boundaries[group_end_idx + 1]
                else:
                    tentative_end_char = total_chars

                group_chars = tentative_end_char - group_start_char
                if group_chars > chunk_size and group_end_idx > group_start_idx:
                    # This chapter would exceed limit; stop before it
                    break
                group_end_idx += 1

            # Determine char range for this chunk
            chunk_start_char = group_start_char
            if group_end_idx < total_chapters:
                chunk_end_char = boundaries[group_end_idx]
            else:
                chunk_end_char = total_chars

            start_byte = _char_to_byte_offset(chunk_start_char)
            end_byte = _char_to_byte_offset(chunk_end_char)

            chunks.append(
                ChunkInfo(
                    chunk_id=chunk_id,
                    start_offset=start_byte,
                    end_offset=end_byte,
                    char_count=chunk_end_char - chunk_start_char,
                    chapter_range=(group_start_idx + 1, group_end_idx),
                )
            )

            chunk_id += 1
            group_start_idx = group_end_idx

        # Handle text before the first chapter boundary
        if boundaries[0] > 0:
            preamble_end_byte = _char_to_byte_offset(boundaries[0])
            preamble_chunk = ChunkInfo(
                chunk_id=-1,  # will be renumbered
                start_offset=0,
                end_offset=preamble_end_byte,
                char_count=boundaries[0],
                chapter_range=None,
            )
            # Prepend and renumber
            chunks.insert(0, preamble_chunk)
            for i, c in enumerate(chunks):
                c.chunk_id = i
    else:
        # No chapter boundaries: fixed-size chunking with overlap
        chunk_id = 0
        pos = 0

        while pos < total_chars:
            end_pos = min(pos + chunk_size, total_chars)

            # Try to find a paragraph break near the end
            if end_pos < total_chars:
                search_start = max(end_pos - 500, pos)
                search_region = text[search_start:end_pos]
                last_para = search_region.rfind("\n\n")
                if last_para != -1:
                    end_pos = search_start + last_para + 2

            start_byte = _char_to_byte_offset(pos)
            end_byte = _char_to_byte_offset(end_pos)

            chunks.append(
                ChunkInfo(
                    chunk_id=chunk_id,
                    start_offset=start_byte,
                    end_offset=end_byte,
                    char_count=end_pos - pos,
                    chapter_range=None,
                )
            )

            chunk_id += 1
            # Advance with overlap
            pos = end_pos - overlap_size if end_pos < total_chars else total_chars

    return ChunkingResult(
        total_chars=total_chars,
        total_chapters=total_chapters,
        chunks=chunks,
        chapter_boundaries=boundaries,
        encoding=encoding,
    )


def load_chunk_text(file_path: Path, chunk: ChunkInfo, encoding: str = "utf-8") -> str:
    """Lazily load text for a specific chunk by byte offset.

    Args:
        file_path: Path to the source novel file.
        chunk: ChunkInfo with byte offsets.
        encoding: File encoding.

    Returns:
        The text content of the chunk.
    """
    with file_path.open("rb") as f:
        f.seek(chunk.start_offset)
        raw = f.read(chunk.end_offset - chunk.start_offset)
    return raw.decode(encoding)


def get_chunk_sample_indices(total_chunks: int, max_samples: int = 25) -> list[int]:
    """Select chunk indices for sampling large files.

    Strategy: first 3 + last 2 + evenly spaced from the middle.

    Args:
        total_chunks: Total number of chunks.
        max_samples: Maximum number of samples to return.

    Returns:
        Sorted list of chunk indices to sample.
    """
    if total_chunks <= max_samples:
        return list(range(total_chunks))

    indices: set[int] = set()

    # First 3
    for i in range(min(3, total_chunks)):
        indices.add(i)

    # Last 2
    for i in range(max(0, total_chunks - 2), total_chunks):
        indices.add(i)

    # Middle: evenly spaced
    remaining = max_samples - len(indices)
    if remaining > 0:
        middle_start = 3
        middle_end = total_chunks - 2
        if middle_end > middle_start:
            step = max(1, (middle_end - middle_start) // (remaining + 1))
            pos = middle_start
            while pos < middle_end and len(indices) < max_samples:
                indices.add(pos)
                pos += step

    return sorted(indices)
