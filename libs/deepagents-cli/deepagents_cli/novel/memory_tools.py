"""Memory tools for novel writing.

This module provides tools for the agent to manage its own memory:
- remember: Store important information
- recall: Retrieve stored information
- forget: Remove outdated information
- update_progress: Update project progress

Memory is organized by categories:
- character: 角色信息（状态、关系、能力变化）
- plot: 剧情信息（主线、支线、已发生事件）
- foreshadow: 伏笔信息（埋下的伏笔、回收状态）
- setting: 设定信息（世界观细节、规则）
- decision: 决策记录（用户的选择、剧情分支）
- summary: 摘要信息（章节摘要、大纲摘要）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

if TYPE_CHECKING:
    from deepagents_cli.novel.project import NovelProject

# 记忆存储路径（项目级别）
_memory_store: dict[str, dict[str, Any]] = {}
_memory_file: Path | None = None
_project_path: Path | None = None
_project_ref: "NovelProject | None" = None


def init_memory_store(project_path: Path) -> None:
    """Initialize memory store for a project.

    Args:
        project_path: Path to the novel project
    """
    global _memory_store, _memory_file, _project_path, _project_ref

    _project_path = project_path
    _project_ref = None  # Will be loaded lazily

    memory_dir = project_path / ".novel" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    _memory_file = memory_dir / "memory.json"

    if _memory_file.exists():
        try:
            _memory_store = json.loads(_memory_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _memory_store = {}
    else:
        _memory_store = {}


def _get_project() -> "NovelProject | None":
    """Get the current project instance, loading lazily if needed."""
    global _project_ref

    if _project_ref is not None:
        return _project_ref

    if _project_path is None:
        return None

    # Lazy import to avoid circular dependency
    from deepagents_cli.novel.project import NovelProject

    try:
        _project_ref = NovelProject.load(_project_path)
        return _project_ref
    except FileNotFoundError:
        return None


def _save_memory() -> None:
    """Save memory to disk."""
    if _memory_file:
        _memory_file.write_text(
            json.dumps(_memory_store, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


def _sync_to_project_state(category: str, key: str, content: str, action: str = "add") -> None:
    """Sync memory changes to project state.

    This ensures consistency between memory tools and project state.

    Args:
        category: Memory category
        key: Memory key
        content: Memory content
        action: "add", "update", or "delete"
    """
    project = _get_project()
    if project is None:
        return

    state = project.state

    if category == "character":
        # Sync character info to project state
        if action == "delete":
            if key in state.characters:
                del state.characters[key]
        else:
            # Parse character status from content
            from deepagents_cli.novel.project import CharacterState

            if key not in state.characters:
                state.characters[key] = CharacterState(name=key)

            char = state.characters[key]

            # Try to extract status from content
            content_lower = content.lower()
            if "收服" in content or "加入" in content:
                char.status = "已收服"
            elif "敌对" in content or "对立" in content or "敌人" in content:
                char.status = "敌对"
            elif "死亡" in content or "牺牲" in content:
                char.status = "死亡"
            elif "中立" in content:
                char.status = "中立"

            # Update last appearance chapter
            import re
            chapter_match = re.search(r"第(\d+)章", content)
            if chapter_match:
                char.last_appearance = int(chapter_match.group(1))

        project.save_state()

    elif category == "foreshadow":
        # Sync foreshadow info to project state
        if action == "delete":
            # Mark as resolved or remove
            for f in state.foreshadowing:
                if f.get("name") == key or f.get("content", "").startswith(key):
                    f["resolved"] = True
                    break
        else:
            # Parse chapter from content
            import re
            chapter_match = re.search(r"第(\d+)章", content)
            chapter = int(chapter_match.group(1)) if chapter_match else state.current_chapter

            # Check if this foreshadow already exists
            exists = False
            for f in state.foreshadowing:
                if f.get("name") == key:
                    f["content"] = content
                    f["chapter"] = chapter
                    exists = True
                    break

            if not exists:
                state.foreshadowing.append({
                    "name": key,
                    "content": content,
                    "chapter": chapter,
                    "resolved": False,
                })

        project.save_state()


def _get_category_display_name(category: str) -> str:
    """Get Chinese display name for category."""
    names = {
        "character": "角色",
        "plot": "剧情",
        "foreshadow": "伏笔",
        "setting": "设定",
        "decision": "决策",
        "summary": "摘要",
    }
    return names.get(category, category)


# ============================================================================
# Memory Tools
# ============================================================================

@tool
def remember(category: str, key: str, content: str) -> str:
    """记住重要信息，以便后续创作时使用。

    在以下情况使用此工具：
    - 角色状态变化（收服、死亡、能力提升）
    - 重要剧情发生（事件、冲突、转折）
    - 埋下伏笔
    - 用户做出重要决策
    - 完成章节后记录摘要

    Args:
        category: 类别，必须是以下之一：
            - character: 角色信息（状态、关系、能力）
            - plot: 剧情信息（事件、冲突）
            - foreshadow: 伏笔信息
            - setting: 设定信息
            - decision: 用户决策
            - summary: 章节/大纲摘要
        key: 标识符，如角色名、章节号、伏笔名称
        content: 要记住的内容

    Returns:
        确认信息

    Examples:
        remember("character", "索隆", "第5章被主角收服，原因是主角展示了超越其的剑术")
        remember("foreshadow", "老鼠的秘密交易", "第3章埋下，老鼠与某势力有秘密交易，待回收")
        remember("decision", "收服策略", "用户选择了平衡策略：收服索隆但不阻挠路飞")
        remember("summary", "第5章", "主角收服索隆，晋升一等兵，发现老鼠与海贼有勾结")
    """
    valid_categories = ["character", "plot", "foreshadow", "setting", "decision", "summary"]

    if category not in valid_categories:
        return f"错误：类别必须是 {valid_categories} 之一，收到: {category}"

    if category not in _memory_store:
        _memory_store[category] = {}

    _memory_store[category][key] = {
        "content": content,
        "updated_at": datetime.now().isoformat(),
    }

    _save_memory()

    # Auto-sync character and foreshadow to project state
    if category in ("character", "foreshadow"):
        _sync_to_project_state(category, key, content, action="add")

    category_name = _get_category_display_name(category)
    return f"已记住 [{category_name}] {key}"


@tool
def recall(category: str | None = None, key: str | None = None) -> str:
    """回忆之前记住的信息。

    在以下情况使用此工具：
    - 写新章节前，回忆相关角色状态
    - 检查伏笔是否需要回收
    - 查看用户之前的决策
    - 获取之前章节的摘要

    Args:
        category: 类别（可选）。不填则返回所有类别的概览。
            可选值: character, plot, foreshadow, setting, decision, summary
        key: 标识符（可选）。不填则返回该类别下所有条目。

    Returns:
        记忆内容

    Examples:
        recall() → 返回所有记忆的概览
        recall("character") → 返回所有角色信息
        recall("character", "索隆") → 返回索隆的信息
        recall("foreshadow") → 返回所有伏笔
    """
    if not _memory_store:
        return "记忆为空，还没有记住任何信息。"

    # 返回所有类别概览
    if category is None:
        lines = ["【记忆概览】\n"]
        for cat, items in _memory_store.items():
            cat_name = _get_category_display_name(cat)
            lines.append(f"## {cat_name} ({len(items)} 条)")
            for k in list(items.keys())[:5]:  # 每类最多显示5条
                content = items[k]["content"]
                preview = content[:50] + "..." if len(content) > 50 else content
                lines.append(f"  - {k}: {preview}")
            if len(items) > 5:
                lines.append(f"  - ...还有 {len(items) - 5} 条")
            lines.append("")
        return "\n".join(lines)

    # 检查类别是否存在
    if category not in _memory_store:
        cat_name = _get_category_display_name(category)
        return f"[{cat_name}] 类别下没有记忆。"

    items = _memory_store[category]
    cat_name = _get_category_display_name(category)

    # 返回特定条目
    if key is not None:
        if key not in items:
            return f"[{cat_name}] 中没有找到 '{key}'。\n现有条目: {list(items.keys())}"
        item = items[key]
        return f"【{cat_name} - {key}】\n{item['content']}\n\n(更新于: {item['updated_at']})"

    # 返回类别下所有条目
    lines = [f"【{cat_name}】共 {len(items)} 条\n"]
    for k, item in items.items():
        lines.append(f"### {k}")
        lines.append(item["content"])
        lines.append(f"(更新于: {item['updated_at']})")
        lines.append("")

    return "\n".join(lines)


@tool
def forget(category: str, key: str) -> str:
    """删除过时或错误的记忆。

    在以下情况使用此工具：
    - 伏笔已回收，删除伏笔记录
    - 角色信息已过时，需要删除旧记录
    - 记忆内容有误，需要删除后重新记录

    Args:
        category: 类别 (character/plot/foreshadow/setting/decision/summary)
        key: 要删除的条目标识符

    Returns:
        确认信息

    Examples:
        forget("foreshadow", "老鼠的秘密交易")  # 伏笔已回收
    """
    if category not in _memory_store:
        cat_name = _get_category_display_name(category)
        return f"[{cat_name}] 类别不存在。"

    if key not in _memory_store[category]:
        cat_name = _get_category_display_name(category)
        return f"[{cat_name}] 中没有找到 '{key}'。"

    del _memory_store[category][key]

    # 如果类别为空，删除类别
    if not _memory_store[category]:
        del _memory_store[category]

    _save_memory()

    # Auto-sync character and foreshadow to project state
    if category in ("character", "foreshadow"):
        _sync_to_project_state(category, key, "", action="delete")

    cat_name = _get_category_display_name(category)
    return f"已删除 [{cat_name}] {key}"


@tool
def update_memory(category: str, key: str, content: str) -> str:
    """更新已有的记忆内容。

    与 remember 的区别：
    - remember: 新增或覆盖
    - update_memory: 追加内容到已有记忆

    Args:
        category: 类别
        key: 标识符
        content: 要追加的内容

    Returns:
        确认信息

    Examples:
        update_memory("character", "索隆", "第8章：学会了新的剑技")
    """
    if category not in _memory_store or key not in _memory_store[category]:
        # 如果不存在，等同于 remember
        return remember.invoke({"category": category, "key": key, "content": content})

    # 追加内容
    old_content = _memory_store[category][key]["content"]
    new_content = f"{old_content}\n\n---\n{content}"

    _memory_store[category][key] = {
        "content": new_content,
        "updated_at": datetime.now().isoformat(),
    }

    _save_memory()

    # Auto-sync character and foreshadow to project state
    if category in ("character", "foreshadow"):
        _sync_to_project_state(category, key, new_content, action="update")

    cat_name = _get_category_display_name(category)
    return f"已更新 [{cat_name}] {key}"


# ============================================================================
# Character Tools
# ============================================================================

@tool
def update_character(
    name: str,
    status: str | None = None,
    location: str | None = None,
    power_level: str | None = None,
    note: str | None = None,
    chapter: int | None = None,
) -> str:
    """更新角色状态。

    在角色状态发生变化时使用此工具，自动同步到项目状态和记忆系统。

    Args:
        name: 角色名称
        status: 角色状态（已收服/敌对/中立/死亡/未出场）
        location: 角色当前位置
        power_level: 角色实力等级
        note: 本次变化的备注/说明
        chapter: 发生变化的章节（不填则使用当前章节）

    Returns:
        确认信息

    Examples:
        update_character("索隆", status="已收服", note="第5章被主角收服")
        update_character("路飞", location="东海", power_level="悬赏3000万")
        update_character("老鼠上校", status="死亡", chapter=15, note="被主角击杀")
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。"

    from deepagents_cli.novel.project import CharacterState

    state = project.state
    current_ch = chapter if chapter is not None else state.current_chapter

    # Get or create character
    if name not in state.characters:
        state.characters[name] = CharacterState(name=name)

    char = state.characters[name]
    updates = []

    if status is not None:
        char.status = status
        updates.append(f"状态: {status}")

    if location is not None:
        char.location = location
        updates.append(f"位置: {location}")

    if power_level is not None:
        char.power_level = power_level
        updates.append(f"实力: {power_level}")

    char.last_appearance = current_ch

    if not updates:
        return "未指定任何更新项。请至少提供 status、location 或 power_level 之一。"

    # Save project state
    project.save_state()

    # Also save to memory for cross-session persistence
    memory_content = f"第{current_ch}章: " + ", ".join(updates)
    if note:
        memory_content += f"\n备注: {note}"

    # Use update_memory to append (or remember if new)
    if "character" in _memory_store and name in _memory_store["character"]:
        update_memory.invoke({"category": "character", "key": name, "content": memory_content})
    else:
        remember.invoke({"category": "character", "key": name, "content": memory_content})

    result_lines = [
        f"✅ 角色状态已更新: {name}",
        "",
    ]
    result_lines.extend([f"  - {u}" for u in updates])
    result_lines.append(f"  - 章节: 第{current_ch}章")
    if note:
        result_lines.append(f"  - 备注: {note}")

    return "\n".join(result_lines)


@tool
def get_character(name: str) -> str:
    """获取角色详细信息。

    Args:
        name: 角色名称

    Returns:
        角色详细信息

    Examples:
        get_character("索隆")
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。"

    state = project.state

    if name not in state.characters:
        # Check if in memory
        if "character" in _memory_store and name in _memory_store["character"]:
            item = _memory_store["character"][name]
            return f"【角色】{name}\n\n{item['content']}\n\n(最后更新: {item['updated_at']})"
        return f"未找到角色: {name}"

    char = state.characters[name]

    lines = [
        f"【角色】{name}",
        "",
        f"状态: {char.status}",
        f"位置: {char.location}",
        f"实力: {char.power_level}",
        f"最后出场: 第{char.last_appearance}章",
    ]

    if char.relationships:
        lines.append("")
        lines.append("关系:")
        for target, relation in char.relationships.items():
            lines.append(f"  - {target}: {relation}")

    # Add memory content if available
    if "character" in _memory_store and name in _memory_store["character"]:
        lines.append("")
        lines.append("【记忆记录】")
        lines.append(_memory_store["character"][name]["content"])

    return "\n".join(lines)


@tool
def list_characters(status_filter: str | None = None) -> str:
    """列出所有角色。

    Args:
        status_filter: 按状态筛选（已收服/敌对/中立/死亡/未出场），不填则显示全部

    Returns:
        角色列表

    Examples:
        list_characters()  # 全部角色
        list_characters("已收服")  # 只看已收服的
    """
    project = _get_project()
    if project is None:
        # Fallback to memory
        if "character" not in _memory_store or not _memory_store["character"]:
            return "暂无角色记录。"

        lines = ["【角色列表】(来自记忆)\n"]
        for name, item in _memory_store["character"].items():
            content = item["content"]
            if len(content) > 80:
                content = content[:80] + "..."
            lines.append(f"- {name}: {content}")
        return "\n".join(lines)

    state = project.state

    if not state.characters:
        return "暂无角色记录。"

    # Group by status
    by_status: dict[str, list[str]] = {}
    for name, char in state.characters.items():
        if status_filter and char.status != status_filter:
            continue
        if char.status not in by_status:
            by_status[char.status] = []
        by_status[char.status].append(f"{name} (位置: {char.location}, 第{char.last_appearance}章)")

    if not by_status:
        return f"没有状态为 '{status_filter}' 的角色。"

    lines = ["【角色列表】\n"]

    # Order: 已收服, 中立, 敌对, 死亡, 未出场
    status_order = ["已收服", "中立", "敌对", "死亡", "未出场"]
    for status in status_order:
        if status in by_status:
            emoji = {"已收服": "✅", "中立": "➖", "敌对": "⚔️", "死亡": "💀", "未出场": "❓"}.get(status, "")
            lines.append(f"{emoji} {status} ({len(by_status[status])}人)")
            for char_info in by_status[status]:
                lines.append(f"   - {char_info}")
            lines.append("")

    return "\n".join(lines)


@tool
def add_relationship(character: str, target: str, relation: str) -> str:
    """添加角色关系。

    Args:
        character: 角色名称
        target: 关系目标角色
        relation: 关系描述（如"同伴"、"敌人"、"师徒"）

    Returns:
        确认信息

    Examples:
        add_relationship("索隆", "路飞", "同伴")
        add_relationship("主角", "索隆", "收服关系")
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。"

    from deepagents_cli.novel.project import CharacterState

    state = project.state

    if character not in state.characters:
        state.characters[character] = CharacterState(name=character)

    state.characters[character].relationships[target] = relation
    project.save_state()

    return f"✅ 已添加关系: {character} → {target}: {relation}"


# ============================================================================
# Foreshadow Tools
# ============================================================================

@tool
def plant_foreshadow(
    name: str,
    content: str,
    chapter: int | None = None,
    target_chapter: int | None = None,
) -> str:
    """埋下伏笔。

    在剧情中埋下伏笔时使用此工具，方便后续追踪和回收。

    Args:
        name: 伏笔名称/标识符（如"神秘老人的预言"、"消失的戒指"）
        content: 伏笔内容描述
        chapter: 埋下伏笔的章节（不填则使用当前章节）
        target_chapter: 预计回收的章节（可选）

    Returns:
        确认信息

    Examples:
        plant_foreshadow("神秘信件", "主角收到一封没有署名的信，暗示其身世")
        plant_foreshadow("老鼠的秘密", "老鼠上校与某势力有秘密交易", target_chapter=15)
    """
    project = _get_project()
    current_ch = chapter
    if current_ch is None:
        if project:
            current_ch = project.state.current_chapter
        else:
            current_ch = 1

    # Build content with chapter info
    full_content = f"第{current_ch}章埋下: {content}"
    if target_chapter:
        full_content += f"\n预计第{target_chapter}章回收"

    # Use remember to store (which will auto-sync to project state)
    result = remember.invoke({
        "category": "foreshadow",
        "key": name,
        "content": full_content
    })

    return f"📌 伏笔已埋下: {name}\n   章节: 第{current_ch}章" + (f"\n   预计回收: 第{target_chapter}章" if target_chapter else "")


@tool
def resolve_foreshadow(name: str, resolved_chapter: int | None = None, resolution: str | None = None) -> str:
    """回收伏笔。

    当伏笔被揭示/回收时使用此工具。

    Args:
        name: 伏笔名称
        resolved_chapter: 回收的章节（不填则使用当前章节）
        resolution: 回收方式/结果描述（可选）

    Returns:
        确认信息

    Examples:
        resolve_foreshadow("神秘信件", resolution="揭示是主角失散多年的父亲所写")
        resolve_foreshadow("老鼠的秘密", resolved_chapter=15)
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。"

    current_ch = resolved_chapter
    if current_ch is None:
        current_ch = project.state.current_chapter

    # Update in memory
    if "foreshadow" in _memory_store and name in _memory_store["foreshadow"]:
        old_content = _memory_store["foreshadow"][name]["content"]
        resolution_text = f"\n\n---\n第{current_ch}章已回收"
        if resolution:
            resolution_text += f": {resolution}"

        _memory_store["foreshadow"][name]["content"] = old_content + resolution_text
        _memory_store["foreshadow"][name]["resolved"] = True
        _memory_store["foreshadow"][name]["resolved_chapter"] = current_ch
        _memory_store["foreshadow"][name]["updated_at"] = datetime.now().isoformat()
        _save_memory()

    # Update in project state
    state = project.state
    for f in state.foreshadowing:
        if f.get("name") == name:
            f["resolved"] = True
            f["resolved_chapter"] = current_ch
            if resolution:
                f["resolution"] = resolution
            break

    project.save_state()

    return f"✅ 伏笔已回收: {name}\n   回收章节: 第{current_ch}章" + (f"\n   回收方式: {resolution}" if resolution else "")


@tool
def list_foreshadows(include_resolved: bool = False) -> str:
    """列出所有伏笔。

    Args:
        include_resolved: 是否包含已回收的伏笔，默认只显示待回收的

    Returns:
        伏笔列表

    Examples:
        list_foreshadows()  # 只看待回收的
        list_foreshadows(include_resolved=True)  # 看全部
    """
    project = _get_project()
    if project is None:
        # Fallback to memory store
        if "foreshadow" not in _memory_store or not _memory_store["foreshadow"]:
            return "暂无伏笔记录。"

        lines = ["【伏笔列表】\n"]
        for name, item in _memory_store["foreshadow"].items():
            resolved = item.get("resolved", False)
            if not include_resolved and resolved:
                continue
            status = "✅ 已回收" if resolved else "📌 待回收"
            lines.append(f"{status} {name}")
            content = item["content"]
            if len(content) > 100:
                content = content[:100] + "..."
            lines.append(f"   {content}")
            lines.append("")
        return "\n".join(lines)

    state = project.state
    if not state.foreshadowing:
        return "暂无伏笔记录。"

    pending = []
    resolved = []

    for f in state.foreshadowing:
        if f.get("resolved", False):
            resolved.append(f)
        else:
            pending.append(f)

    lines = []

    if pending:
        lines.append(f"【待回收伏笔】({len(pending)}个)\n")
        for f in pending:
            lines.append(f"📌 {f.get('name', f.get('content', '')[:20])}")
            lines.append(f"   第{f.get('chapter', '?')}章: {f.get('content', '')[:50]}...")
            lines.append("")

    if include_resolved and resolved:
        lines.append(f"\n【已回收伏笔】({len(resolved)}个)\n")
        for f in resolved:
            lines.append(f"✅ {f.get('name', f.get('content', '')[:20])}")
            lines.append(f"   埋下: 第{f.get('chapter', '?')}章 → 回收: 第{f.get('resolved_chapter', '?')}章")
            if f.get("resolution"):
                lines.append(f"   回收方式: {f['resolution']}")
            lines.append("")

    if not lines:
        return "暂无伏笔记录。"

    return "\n".join(lines)


# ============================================================================
# Progress Tools
# ============================================================================

@tool
def update_progress(
    current_chapter: int | None = None,
    outline_completed: int | None = None,
    outline_total: int | None = None,
    writing_completed: int | None = None,
    writing_total: int | None = None,
    last_chapter_summary: str | None = None,
) -> str:
    """更新项目进度状态。

    在以下情况使用此工具：
    - 完成一章大纲后，更新 outline_completed
    - 完成一章正文后，更新 writing_completed 和 current_chapter
    - 设定总章节数时，更新 outline_total 和 writing_total
    - 完成章节后，更新 last_chapter_summary

    Args:
        current_chapter: 当前正在写的章节号
        outline_completed: 已完成的大纲章节数
        outline_total: 大纲总章节数
        writing_completed: 已完成的正文章节数
        writing_total: 正文总章节数
        last_chapter_summary: 上一章的摘要（用于上下文）

    Returns:
        确认信息，包含更新后的进度

    Examples:
        update_progress(outline_completed=5)  # 完成第5章大纲
        update_progress(writing_completed=3, current_chapter=4)  # 完成第3章，开始写第4章
        update_progress(outline_total=50, writing_total=50)  # 设定总章节数
        update_progress(last_chapter_summary="主角初遇路飞，展现实力")  # 记录摘要
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。请确保已正确初始化项目。"

    state = project.state
    updates = []

    if current_chapter is not None:
        state.current_chapter = current_chapter
        updates.append(f"当前章节 → 第{current_chapter}章")

    if outline_completed is not None:
        state.outline_completed = outline_completed
        updates.append(f"大纲进度 → {outline_completed}章")

    if outline_total is not None:
        state.outline_total = outline_total
        updates.append(f"大纲总数 → {outline_total}章")

    if writing_completed is not None:
        state.writing_completed = writing_completed
        updates.append(f"正文进度 → {writing_completed}章")

    if writing_total is not None:
        state.writing_total = writing_total
        updates.append(f"正文总数 → {writing_total}章")

    if last_chapter_summary is not None:
        state.last_chapter_summary = last_chapter_summary
        updates.append("上章摘要 → 已更新")

    if not updates:
        return "未指定任何更新项。请至少提供一个参数。"

    # Save state
    project.save_state()

    result_lines = ["✓ 进度已更新："]
    result_lines.extend([f"  - {u}" for u in updates])
    result_lines.append("")
    result_lines.append(f"当前状态: 大纲 {state.outline_completed}/{state.outline_total or '?'} 章, "
                       f"正文 {state.writing_completed}/{state.writing_total or '?'} 章")

    return "\n".join(result_lines)


@tool
def get_progress() -> str:
    """获取当前项目进度。

    Returns:
        当前进度状态的详细信息

    Examples:
        get_progress()  # 查看当前进度
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。请确保已正确初始化项目。"

    state = project.state
    config = project.config

    lines = [
        f"【项目进度】《{config.title}》",
        "",
        f"大纲: {state.outline_completed}/{state.outline_total or '未设定'} 章",
        f"正文: {state.writing_completed}/{state.writing_total or '未设定'} 章",
        f"当前: 第 {state.current_chapter} 章",
        "",
    ]

    # 计算完成百分比
    if state.outline_total and state.outline_total > 0:
        outline_pct = state.outline_completed / state.outline_total * 100
        lines.append(f"大纲完成度: {outline_pct:.1f}%")

    if state.writing_total and state.writing_total > 0:
        writing_pct = state.writing_completed / state.writing_total * 100
        lines.append(f"正文完成度: {writing_pct:.1f}%")

    if state.last_chapter_summary:
        lines.append("")
        lines.append("【上章摘要】")
        summary = state.last_chapter_summary
        if len(summary) > 200:
            summary = summary[:200] + "..."
        lines.append(summary)

    return "\n".join(lines)


@tool
def complete_chapter(
    chapter: int,
    content: str,
    summary: str,
    title: str | None = None,
) -> str:
    """完成一章的写作，保存内容并更新进度。

    这是一个便捷工具，自动完成以下操作：
    1. 保存章节内容到文件
    2. 保存章节摘要
    3. 更新项目进度
    4. 记录到记忆系统

    Args:
        chapter: 章节号
        content: 章节正文内容
        summary: 章节摘要（200-500字）
        title: 章节标题（可选）

    Returns:
        确认信息

    Examples:
        complete_chapter(
            chapter=1,
            content="正文内容...",
            summary="主角穿越到海贼世界，获得系统，加入海军",
            title="穿越海贼世界"
        )
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。请确保已正确初始化项目。"

    # 1. Save chapter content
    chapter_header = f"# 第{chapter}章"
    if title:
        chapter_header += f" {title}"
    chapter_header += "\n\n"

    full_content = chapter_header + content
    project.save_chapter(chapter, full_content)

    # 2. Save chapter summary
    project.save_chapter_summary(chapter, summary)

    # 3. Update progress
    state = project.state
    state.writing_completed = max(state.writing_completed, chapter)
    state.current_chapter = chapter + 1
    state.last_chapter_summary = summary
    project.save_state()

    # 4. Record to memory
    chapter_key = f"第{chapter}章"
    if title:
        chapter_key += f" {title}"

    remember.invoke({
        "category": "summary",
        "key": chapter_key,
        "content": summary
    })

    # Calculate word count
    word_count = len(content)

    result_lines = [
        f"✅ 第{chapter}章已完成！",
        "",
        f"📄 内容: {word_count} 字",
        f"📝 摘要: {len(summary)} 字",
        f"💾 文件: chapters/volume-{(chapter - 1) // 50 + 1}/chapter-{chapter:03d}.md",
        "",
        f"📊 当前进度: 正文 {state.writing_completed}/{state.writing_total or '?'} 章",
        f"📍 下一章: 第{state.current_chapter}章",
    ]

    return "\n".join(result_lines)


@tool
def complete_outline(
    chapter: int,
    outline: str,
    title: str | None = None,
) -> str:
    """完成一章的大纲，保存并更新进度。

    Args:
        chapter: 章节号
        outline: 大纲内容
        title: 章节标题（可选）

    Returns:
        确认信息

    Examples:
        complete_outline(
            chapter=1,
            outline="场景1: 穿越\\n场景2: 获得系统\\n场景3: 遇到海军",
            title="穿越海贼世界"
        )
    """
    project = _get_project()
    if project is None:
        return "错误：无法访问项目状态。请确保已正确初始化项目。"

    # Determine volume
    volume = (chapter - 1) // 50 + 1

    # Build outline content
    outline_header = f"# 第{chapter}章大纲"
    if title:
        outline_header += f": {title}"
    outline_header += "\n\n"

    full_outline = outline_header + outline

    # Save outline file
    outline_dir = project.path / "outline" / f"volume-{volume}"
    outline_dir.mkdir(parents=True, exist_ok=True)
    outline_file = outline_dir / f"chapter-{chapter:03d}.md"
    outline_file.write_text(full_outline, encoding="utf-8")

    # Update progress
    state = project.state
    state.outline_completed = max(state.outline_completed, chapter)
    project.save_state()

    result_lines = [
        f"✅ 第{chapter}章大纲已完成！",
        "",
        f"💾 文件: outline/volume-{volume}/chapter-{chapter:03d}.md",
        f"📊 当前进度: 大纲 {state.outline_completed}/{state.outline_total or '?'} 章",
    ]

    return "\n".join(result_lines)


# ============================================================================
# Helper functions for middleware
# ============================================================================

def get_memory_summary() -> str:
    """Get a brief summary of all memories for injection into system prompt."""
    if not _memory_store:
        return ""

    lines = ["【Agent记忆状态】"]

    # 角色
    if "character" in _memory_store:
        chars = list(_memory_store["character"].keys())
        lines.append(f"- 已记录角色: {', '.join(chars[:5])}" + (f" 等{len(chars)}个" if len(chars) > 5 else ""))

    # 伏笔
    if "foreshadow" in _memory_store:
        foreshadows = list(_memory_store["foreshadow"].keys())
        lines.append(f"- 待回收伏笔: {', '.join(foreshadows[:3])}" + (f" 等{len(foreshadows)}个" if len(foreshadows) > 3 else ""))

    # 最近决策
    if "decision" in _memory_store:
        decisions = list(_memory_store["decision"].keys())
        lines.append(f"- 用户决策: {', '.join(decisions[:3])}" + (f" 等{len(decisions)}个" if len(decisions) > 3 else ""))

    # 章节摘要
    if "summary" in _memory_store:
        summaries = list(_memory_store["summary"].keys())
        lines.append(f"- 章节摘要: {len(summaries)} 章")

    lines.append("")
    lines.append("使用 recall() 工具查看详细记忆内容。")

    return "\n".join(lines)


def get_all_memory_tools() -> list:
    """Get all memory tools."""
    return [
        # Memory tools
        remember,
        recall,
        forget,
        update_memory,
        # Character tools
        update_character,
        get_character,
        list_characters,
        add_relationship,
        # Foreshadow tools
        plant_foreshadow,
        resolve_foreshadow,
        list_foreshadows,
        # Progress tools
        update_progress,
        get_progress,
        # Chapter completion tools
        complete_chapter,
        complete_outline,
    ]


__all__ = [
    "init_memory_store",
    # Memory tools
    "remember",
    "recall",
    "forget",
    "update_memory",
    # Character tools
    "update_character",
    "get_character",
    "list_characters",
    "add_relationship",
    # Foreshadow tools
    "plant_foreshadow",
    "resolve_foreshadow",
    "list_foreshadows",
    # Progress tools
    "update_progress",
    "get_progress",
    # Chapter completion tools
    "complete_chapter",
    "complete_outline",
    # Helper functions
    "get_memory_summary",
    "get_all_memory_tools",
]
