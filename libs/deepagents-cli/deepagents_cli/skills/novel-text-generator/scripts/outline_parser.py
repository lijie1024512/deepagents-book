#!/usr/bin/env python3
"""
大纲解析器

用于解析小说大纲文件，提取章节信息以供正文生成使用。

使用方法：
    python outline_parser.py --input outline.md --chapter 3
    python outline_parser.py --input outline.md --chapter 3 --output chapter_info.json
"""

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PlotPoint:
    """情节点"""

    title: str  # 小标题
    description: str  # 具体描述


@dataclass
class ChapterInfo:
    """章节信息"""

    chapter_number: int  # 章节号
    chapter_title: str  # 章节标题
    summary: str  # 章节概述
    plot_points: list[PlotPoint]  # 情节点列表
    emotional_arc: str  # 情感变化
    highlights: list[str]  # 爽点
    hooks: list[str]  # 钩子
    foreshadowing: list[str]  # 伏笔


@dataclass
class VolumeInfo:
    """卷信息"""

    volume_number: int  # 卷号
    volume_title: str  # 卷标题
    core_theme: str  # 核心主题
    core_conflict: str  # 核心冲突
    protagonist_goal: str  # 主角目标
    rewards: str  # 本卷收获
    key_events: list[str]  # 关键事件


def parse_plot_points(text: str) -> list[PlotPoint]:
    """解析情节点列表"""
    plot_points = []

    # 匹配格式：【小标题】描述
    pattern = r"【([^】]+)】\s*(.+?)(?=【|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    for title, desc in matches:
        plot_points.append(PlotPoint(title=title.strip(), description=desc.strip()))

    # 如果上面的格式不匹配，尝试数字列表格式
    if not plot_points:
        # 匹配格式：1. 【小标题】描述 或 1. 描述
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            # 去掉开头的数字和点
            line = re.sub(r"^\d+\.\s*", "", line)
            if line:
                # 检查是否有【小标题】
                match = re.match(r"【([^】]+)】\s*(.+)", line)
                if match:
                    plot_points.append(
                        PlotPoint(title=match.group(1).strip(), description=match.group(2).strip())
                    )
                else:
                    # 没有小标题，使用描述的前几个字作为标题
                    short_title = line[:10] + "..." if len(line) > 10 else line
                    plot_points.append(PlotPoint(title=short_title, description=line))

    return plot_points


def parse_chapter(text: str, chapter_number: int) -> ChapterInfo | None:
    """解析单个章节"""
    # 匹配章节标题
    # 格式：### 第X章：《章节标题》 或 ## 第X章：《章节标题》
    chapter_pattern = rf"###?\s*第{chapter_number}章[：:]\s*《([^》]+)》"
    match = re.search(chapter_pattern, text)

    if not match:
        # 尝试其他格式
        chapter_pattern = rf"###?\s*第{chapter_number}章[：:]?\s*([^\n]+)"
        match = re.search(chapter_pattern, text)

    if not match:
        return None

    chapter_title = match.group(1).strip()
    chapter_start = match.end()

    # 找到下一章的开始位置
    next_chapter_pattern = rf"###?\s*第{chapter_number + 1}章"
    next_match = re.search(next_chapter_pattern, text[chapter_start:])
    if next_match:
        chapter_end = chapter_start + next_match.start()
    else:
        chapter_end = len(text)

    chapter_text = text[chapter_start:chapter_end]

    # 解析章节概述
    summary = ""
    summary_match = re.search(
        r"\*\*章节概述\*\*[：:]\s*(.+?)(?=\*\*|\n\n|$)", chapter_text, re.DOTALL
    )
    if summary_match:
        summary = summary_match.group(1).strip()

    # 解析情节点
    plot_points = []
    plot_match = re.search(r"\*\*情节点\*\*[：:]?\s*\n(.+?)(?=\*\*|$)", chapter_text, re.DOTALL)
    if plot_match:
        plot_points = parse_plot_points(plot_match.group(1))

    # 解析情感变化
    emotional_arc = ""
    emotion_match = re.search(
        r"\*\*情感变化\*\*[：:]\s*(.+?)(?=\*\*|\n\n|$)", chapter_text, re.DOTALL
    )
    if emotion_match:
        emotional_arc = emotion_match.group(1).strip()

    # 解析爽点
    highlights = []
    highlight_match = re.search(r"\*\*爽点\*\*[：:]?\s*\n(.+?)(?=\*\*|$)", chapter_text, re.DOTALL)
    if highlight_match:
        highlight_text = highlight_match.group(1)
        for line in highlight_text.strip().split("\n"):
            line = re.sub(r"^\d+\.\s*", "", line.strip())
            if line:
                highlights.append(line)

    # 解析钩子
    hooks = []
    hook_match = re.search(r"\*\*钩子\*\*[：:]\s*(.+?)(?=\*\*|\n\n|$)", chapter_text, re.DOTALL)
    if hook_match:
        hooks.append(hook_match.group(1).strip())

    # 解析伏笔
    foreshadowing = []
    foreshadow_match = re.search(r"\*\*伏笔\*\*[：:]?\s*\n(.+?)(?=\*\*|$)", chapter_text, re.DOTALL)
    if foreshadow_match:
        foreshadow_text = foreshadow_match.group(1)
        for line in foreshadow_text.strip().split("\n"):
            line = re.sub(r"^\d+\.\s*", "", line.strip())
            if line:
                foreshadowing.append(line)

    return ChapterInfo(
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        summary=summary,
        plot_points=plot_points,
        emotional_arc=emotional_arc,
        highlights=highlights,
        hooks=hooks,
        foreshadowing=foreshadowing,
    )


def parse_volume(text: str, volume_number: int) -> VolumeInfo | None:
    """解析卷概述"""
    # 匹配卷标题
    volume_pattern = rf"###?\s*第{volume_number}卷[：:]\s*([^\n（(]+)"
    match = re.search(volume_pattern, text)

    if not match:
        # 尝试简化格式
        volume_pattern = rf"###?\s*第{volume_number}卷"
        match = re.search(volume_pattern, text)

    if not match:
        return None

    volume_title = match.group(1).strip() if match.lastindex else f"第{volume_number}卷"
    volume_start = match.end()

    # 找到下一卷或章节的开始位置
    next_pattern = rf"###?\s*第(?:{volume_number + 1}卷|\d+章)"
    next_match = re.search(next_pattern, text[volume_start:])
    if next_match:
        volume_end = volume_start + next_match.start()
    else:
        volume_end = len(text)

    volume_text = text[volume_start:volume_end]

    # 解析各字段
    def extract_field(field_name: str) -> str:
        pattern = rf"\*\*{field_name}\*\*[：:]\s*(.+?)(?=\*\*|\n\n|$)"
        field_match = re.search(pattern, volume_text, re.DOTALL)
        return field_match.group(1).strip() if field_match else ""

    core_theme = extract_field("核心主题")
    core_conflict = extract_field("核心冲突")
    protagonist_goal = extract_field("主角目标")
    rewards = extract_field("本卷收获")

    # 解析关键事件
    key_events = []
    events_match = re.search(
        r"\*\*关键事件\*\*[：:]?\s*\n(.+?)(?=\*\*|###|$)", volume_text, re.DOTALL
    )
    if events_match:
        events_text = events_match.group(1)
        for line in events_text.strip().split("\n"):
            line = re.sub(r"^\d+\.\s*", "", line.strip())
            if line:
                key_events.append(line)

    return VolumeInfo(
        volume_number=volume_number,
        volume_title=volume_title,
        core_theme=core_theme,
        core_conflict=core_conflict,
        protagonist_goal=protagonist_goal,
        rewards=rewards,
        key_events=key_events,
    )


def format_chapter_info(chapter: ChapterInfo) -> str:
    """格式化章节信息为可读文本"""
    lines = []

    lines.append(f"# 第{chapter.chapter_number}章：《{chapter.chapter_title}》")
    lines.append("")

    if chapter.summary:
        lines.append("## 章节概述")
        lines.append(chapter.summary)
        lines.append("")

    if chapter.plot_points:
        lines.append(f"## 情节点 ({len(chapter.plot_points)}个)")
        for i, pp in enumerate(chapter.plot_points, 1):
            lines.append(f"{i}. 【{pp.title}】{pp.description}")
        lines.append("")

    if chapter.emotional_arc:
        lines.append("## 情感变化")
        lines.append(chapter.emotional_arc)
        lines.append("")

    if chapter.highlights:
        lines.append("## 爽点")
        for i, h in enumerate(chapter.highlights, 1):
            lines.append(f"{i}. {h}")
        lines.append("")

    if chapter.hooks:
        lines.append("## 钩子")
        for hook in chapter.hooks:
            lines.append(f"- {hook}")
        lines.append("")

    if chapter.foreshadowing:
        lines.append("## 伏笔")
        for i, f in enumerate(chapter.foreshadowing, 1):
            lines.append(f"{i}. {f}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="大纲解析器")
    parser.add_argument("--input", "-i", required=True, help="输入大纲文件路径")
    parser.add_argument("--chapter", "-c", type=int, help="要解析的章节号")
    parser.add_argument("--volume", "-v", type=int, help="要解析的卷号")
    parser.add_argument("--output", "-o", help="输出文件路径（可选）")
    parser.add_argument("--format", "-f", choices=["json", "text"], default="text", help="输出格式")

    args = parser.parse_args()

    # 读取文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误：文件不存在 - {args.input}")
        return 1

    text = input_path.read_text(encoding="utf-8")

    result = None

    if args.chapter:
        chapter = parse_chapter(text, args.chapter)
        if not chapter:
            print(f"错误：未找到第{args.chapter}章")
            return 1
        result = chapter

    elif args.volume:
        volume = parse_volume(text, args.volume)
        if not volume:
            print(f"错误：未找到第{args.volume}卷")
            return 1
        result = volume

    else:
        print("错误：请指定 --chapter 或 --volume 参数")
        return 1

    # 输出结果
    if args.format == "json":
        output_text = json.dumps(asdict(result), ensure_ascii=False, indent=2)
    else:
        if isinstance(result, ChapterInfo):
            output_text = format_chapter_info(result)
        else:
            output_text = json.dumps(asdict(result), ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_text, encoding="utf-8")
        print(f"结果已保存至：{args.output}")
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    exit(main())
