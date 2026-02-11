# Hooks系统设计文档

## 概述

本文档介绍了小说创作CLI工具的Hooks系统设计，该系统借鉴了 [planning-with-files](https://github.com/OthmanAdi/planning-with-files) 项目的设计理念，并针对小说创作场景进行了改进和优化。

---

## 一、Planning with Files 设计思路

### 1.1 核心理念

Planning with Files 项目的核心设计理念是：

> **"Context Window = RAM (volatile), Filesystem = Disk (persistent)"**
>
> 上下文窗口相当于内存（易失），文件系统相当于磁盘（持久化）

这一理念解决了AI Agent在长时间任务中的关键问题：**上下文丢失导致的任务中断和状态不一致**。

### 1.2 三文件模式 (Three-File Pattern)

Planning with Files 使用三个核心文件来管理任务状态：

| 文件 | 用途 | 内容 |
|-----|------|------|
| `task_plan.md` | 任务规划 | 阶段划分、进度追踪、待办事项 |
| `findings.md` | 发现记录 | 研究结果、决策理由、技术细节 |
| `progress.md` | 会话日志 | 每次会话的操作记录、错误信息 |

### 1.3 Hooks机制

Planning with Files 通过 Claude 的 Hooks 机制实现自动化：

#### PreToolUse Hook
在执行工具前自动触发：
```bash
# 在执行重要操作前读取计划文件
if tool_name in ["Write", "Edit", "Bash"]:
    read_file("task_plan.md")
```

#### PostToolUse Hook
在工具执行后自动触发：
```bash
# 在完成操作后提醒更新状态
echo "⏰ Remember to update progress.md with this result"
```

#### Stop Hook
在Agent停止时触发：
```bash
# 验证任务完成状态
check_completion_status()
```

### 1.4 2-Action Rule（两动作规则）

> 每执行2次 view/browser/search 操作后，必须将发现保存到文件

这个规则确保了：
- 重要信息不会丢失在上下文中
- 强制Agent定期"思考并记录"
- 防止信息过载导致的遗忘

### 1.5 5-Question Reboot Check（5问重启检查）

在会话恢复时，必须回答5个问题：

1. **Where am I?** - 我在代码库的哪个位置？
2. **What was I doing?** - 我之前在做什么？
3. **What have I discovered?** - 我发现了什么？
4. **What's left to do?** - 还剩什么要做？
5. **What problems emerged?** - 出现了什么问题？

### 1.6 3-Strike Error Protocol（三振出局协议）

连续错误处理策略：
1. 第一次错误：诊断根本原因
2. 第二次错误：尝试替代方案
3. 第三次错误：质疑基本假设
4. 仍然失败：向用户升级

---

## 二、当前系统改进点

### 2.1 架构对比

| 特性 | Planning with Files | 本项目改进 |
|-----|---------------------|-----------|
| 存储方式 | 纯文件 (Markdown) | SQLite + 文件混合 |
| 事务支持 | 无 | ACID事务 |
| 并发安全 | 无 | WAL模式 |
| 状态一致性 | 依赖手动维护 | 自动同步 |
| 检查点 | 无 | 自动检查点 |
| 领域特化 | 通用任务 | 小说创作专用 |

### 2.2 SQLite 替代纯文件存储

**Planning with Files 的问题**：
- 多文件同步可能导致状态不一致
- 崩溃时可能丢失部分写入
- 无法实现原子操作

**本项目改进**：
```python
class NovelDatabase:
    """SQLite数据库，提供ACID保证"""

    def __init__(self, project_path: Path):
        self.db_path = project_path / ".novel" / "novel.db"
        # 启用WAL模式，支持并发读写
        conn.execute("PRAGMA journal_mode=WAL")
```

### 2.3 领域特化的Hooks

Planning with Files 的 Hooks 是通用的，本项目针对小说创作进行了特化：

#### PreToolUse Hooks

```python
def _pre_write_chapter_hook(chapter: int) -> str | None:
    """写章节前自动收集上下文"""
    context_parts = []

    # 1. 上一章摘要
    if last_summary:
        context_parts.append(f"【上一章摘要】{last_summary}")

    # 2. 本章大纲
    if outline_exists:
        context_parts.append(f"【第{chapter}章大纲】{outline}")

    # 3. 活跃角色
    recent_chars = get_characters_in_recent_chapters(3)
    if recent_chars:
        context_parts.append("【近期活跃角色】" + format_chars(recent_chars))

    # 4. 临近回收的伏笔
    due_foreshadows = get_foreshadows_due_soon(chapter + 5)
    if due_foreshadows:
        context_parts.append("【临近回收伏笔】" + format_foreshadows(due_foreshadows))

    return "\n".join(context_parts)
```

#### PostToolUse Hooks

```python
def _post_chapter_complete_hook(chapter: int, result: str) -> str:
    """章节完成后自动提醒"""
    reminders = []

    # 1. 检查超期伏笔
    overdue = get_overdue_foreshadows(chapter)
    if overdue:
        reminders.append(f"⚠️ 以下伏笔已超期: {format_foreshadows(overdue)}")

    # 2. 提醒更新角色状态
    reminders.append("📝 如有角色状态变化，请使用 update_character()")

    # 3. 自动检查点
    if should_create_checkpoint():
        checkpoint_id = create_checkpoint(f"第{chapter}章后")
        reminders.append(f"💾 已创建自动检查点 (ID: {checkpoint_id})")

    return result + "\n\n" + "\n".join(reminders)
```

### 2.4 5问重启检查的改进

原版5问检查需要Agent手动填写，本项目实现了**自动化**：

```python
def get_session_recovery_context() -> str:
    """自动生成会话恢复上下文"""

    context = ["【会话恢复上下文】(5问检查)\n"]

    # 1️⃣ 当前位置 - 自动从数据库读取
    progress = db.get_progress()
    context.append(f"1️⃣ 当前位置:")
    context.append(f"   - 大纲进度: {progress.outline}/{progress.outline_total}")
    context.append(f"   - 正文进度: {progress.writing}/{progress.writing_total}")

    # 2️⃣ 上次操作 - 从操作日志读取
    pending = db.get_pending_operations()
    if pending:
        context.append(f"2️⃣ 上次操作 (可能未完成):")
        for op in pending:
            context.append(f"   - {op.operation}: {op.status}")

    # 3️⃣ 已发现的内容 - 从记忆系统读取
    memory = db.recall()
    context.append(f"3️⃣ 已记录的发现:")
    context.append(f"   - 总记忆条目: {count_memory_entries(memory)}")

    # 4️⃣ 待完成事项 - 自动分析
    context.append(f"4️⃣ 待完成事项:")
    context.append(f"   - 待回收伏笔: {count_pending_foreshadows()}")

    # 5️⃣ 问题检查 - 自动检测
    issues = detect_issues()
    context.append(f"5️⃣ 问题检查: {issues or '无明显问题'}")

    return "\n".join(context)
```

### 2.5 自动检查点 vs 手动保存

**Planning with Files**：依赖Agent手动执行保存命令

**本项目改进**：基于2-Action Rule自动创建检查点

```python
# 配置
_hook_state = {
    "operation_count": 0,
    "checkpoint_threshold": 3,  # 每3次重要操作自动保存
}

# 在PostToolUse中自动触发
if operation_count >= checkpoint_threshold:
    db.create_checkpoint(f"自动检查点-第{chapter}章后")
    reset_counter()
```

### 2.6 中间件集成

本项目将Hooks系统集成到了LangGraph中间件架构中：

```python
class NovelMemoryMiddleware(AgentMiddleware):
    """集成Hooks的中间件"""

    def __init__(self, project, enable_hooks=True):
        if enable_hooks:
            self.hooks_registry = NovelHooksRegistry(project.path)

    def before_agent(self, state, runtime, config):
        """会话开始时注入恢复上下文"""
        if self._is_first_call:
            recovery_context = self.hooks_registry.get_recovery_context()
            if recovery_context:
                inject_recovery_message(state, recovery_context)

    def wrap_model_call(self, request, handler):
        """注入Hooks系统说明到系统提示词"""
        auto_context = self._build_auto_context()
        # 包含Hooks系统说明
        hooks_section = build_hooks_system_prompt_section(self.hooks_registry)
        ...
```

---

## 三、功能对照表

| 功能 | Planning with Files | 本项目实现 | 改进说明 |
|-----|---------------------|-----------|---------|
| 任务计划文件 | `task_plan.md` | SQLite `progress` 表 | ACID事务保证 |
| 发现记录 | `findings.md` | SQLite `memory` 表 | 分类存储，快速查询 |
| 会话日志 | `progress.md` | SQLite `operation_log` 表 | 自动记录，支持回滚 |
| PreToolUse Hook | Shell命令读取文件 | Python函数自动注入 | 类型安全，领域特化 |
| PostToolUse Hook | Shell命令提醒 | 增强返回值 | 包含具体待办项 |
| 2-Action Rule | 手动计数 | 自动计数+自动检查点 | 无需Agent干预 |
| 5-Question Check | 手动填写 | 自动生成 | 从数据库读取 |
| 3-Strike Protocol | 手动实现 | 待实现 | 可扩展 |
| 状态恢复 | 读取文件 | 数据库检查点 | 原子恢复 |

---

## 四、使用示例

### 4.1 初始化项目

```python
from deepagents_cli.novel import NovelProject, NovelMemoryMiddleware

# 创建项目
project = NovelProject.init("/path/to/novel", title="海贼同人", world_type="onepiece")

# 创建带Hooks的中间件
middleware = NovelMemoryMiddleware(project, enable_hooks=True)
```

### 4.2 Hooks自动触发

当Agent调用 `complete_chapter()` 工具时：

1. **PreToolUse**（写之前）：自动加载上章摘要、本章大纲、活跃角色
2. **工具执行**：保存章节内容和摘要
3. **PostToolUse**（写之后）：
   - 检查是否有超期伏笔
   - 提醒更新角色状态
   - 自动创建检查点（如果达到阈值）
   - 建议下一步操作

### 4.3 会话恢复

新会话开始时，`before_agent` 自动注入恢复上下文：

```
【会话恢复上下文】(5问检查)

1️⃣ 当前位置:
   - 大纲进度: 10/50章
   - 正文进度: 5/50章
   - 当前章节: 第6章

2️⃣ 上次操作: 无未完成操作

3️⃣ 已记录的发现:
   - 总记忆条目: 23条
   - character: ['李寒', '索隆', '娜美']
   - foreshadow: ['老鼠的秘密']

4️⃣ 待完成事项:
   - 待回收伏笔: 3个
   - 已超期伏笔: 1个 ⚠️
   - 可以开始写第6章正文

5️⃣ 问题检查:
   - 1个伏笔埋下超过20章未回收
```

---

## 五、文件结构

```
deepagents_cli/novel/
├── __init__.py           # 模块导出
├── database.py           # SQLite数据库层
├── hooks.py              # Hooks系统实现 ← 新增
├── memory_middleware.py  # 中间件（集成Hooks）
├── memory_tools.py       # 记忆工具
├── project.py            # 项目管理
├── commands.py           # CLI命令
└── migrate.py            # 迁移工具
```

---

## 六、总结

### 借鉴点

1. **"上下文=内存，文件=磁盘"的设计理念** - 核心思想
2. **三文件模式** - 状态分离的思路
3. **Hooks机制** - 自动化触发
4. **2-Action Rule** - 定期保存策略
5. **5-Question Reboot Check** - 会话恢复框架

### 改进点

1. **SQLite替代纯文件** - ACID保证，并发安全
2. **领域特化Hooks** - 针对小说创作场景优化
3. **自动化5问检查** - 无需手动填写
4. **自动检查点** - 基于操作计数自动触发
5. **中间件集成** - 无缝融入LangGraph架构
6. **类型安全** - Python实现，静态类型检查

### 架构优势

```
Planning with Files          本项目
──────────────────          ────────
  Markdown文件                SQLite
       ↓                         ↓
   手动同步                  自动事务
       ↓                         ↓
   容易不一致               ACID保证
       ↓                         ↓
   手动Hooks              中间件集成
       ↓                         ↓
   通用任务               小说创作特化
```

---

## 附录：Hooks配置

```python
# 默认启用的Hooks
enabled_hooks = {
    "pre_write_chapter",     # 写章节前自动加载上下文
    "pre_outline",           # 写大纲前自动加载框架
    "post_chapter_complete", # 章节完成后提醒检查
    "post_outline_complete", # 大纲完成后提示下一步
    "session_recovery",      # 会话恢复上下文
    "auto_checkpoint",       # 自动创建检查点
}

# 可通过Registry禁用
registry.disable_hook("auto_checkpoint")
```
