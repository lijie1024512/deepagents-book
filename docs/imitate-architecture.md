# 仿写功能 — 项目架构文档与业务流程

## 一、系统总览

仿写功能是 deepagents-cli 的一个子系统，基于 LangGraph Agent 实现。核心理念是：**读源小说 → 分析DNA（文风/技法/金手指） → 提出创意改编方案 → 逐章生成高质量仿写小说**。

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户 (CLI)                              │
│                   deepagents novel start                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    create_imitate_agent()                        │
│                      (agent.py:789)                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │               Middleware Chain (执行顺序)                  │    │
│  │  1. PromptOptimizerMiddleware (marker_mode)               │    │
│  │  2. ImitateMemoryMiddleware (自动上下文注入)               │    │
│  │  3. SummarizationMiddleware (>100k tokens时压缩)          │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                   Tools (12个)                             │    │
│  │  仿写工具 (9): index_source, read_source_chapter,         │    │
│  │    read_source_range, search_source, save_analysis,       │    │
│  │    get_analysis, get_generation_context, save_chapter,    │    │
│  │    log_creative_choice                                     │    │
│  │  记忆工具 (3): remember, recall, forget                    │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │               CompositeBackend (虚拟文件系统)              │    │
│  │  默认路由  → FilesystemBackend (项目目录)                  │    │
│  │  /skills/  → FilesystemBackend (内置技能目录)              │    │
│  │  /history/ → ImitateHistoryBackend (只读, 从SQLite渲染)   │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、目录结构

### 2.1 源码结构

```
libs/deepagents-cli/deepagents_cli/
├── novel/
│   ├── __init__.py                    # 公共API导出
│   ├── project.py                     # NovelProject, NovelConfig, NovelState
│   ├── database.py                    # NovelDatabase (SQLite, WAL模式)
│   ├── chunker.py                     # 源小说索引：编码检测、章节边界扫描、按章读取
│   ├── imitate_tools.py               # 9个仿写工具 (Agent可调用的@tool)
│   ├── imitate_middleware.py          # ImitateMemoryMiddleware (状态感知上下文注入)
│   ├── imitate_history_backend.py     # 只读虚拟文件后端 (/history/)
│   ├── commands.py                    # CLI子命令: init, start, list, status
│   ├── memory_tools.py               # 18个原创模式工具 (仿写仅用3个)
│   ├── memory_middleware.py           # 原创模式中间件 (仿写不用)
│   ├── hooks.py                       # 原创模式hooks (仿写不用)
│   └── migrate.py                     # YAML→SQLite迁移
│
├── skills/                            # SKILL.md 技能文件
│   ├── novel-imitate-orchestrator/    # 仿写编辑技能 (规划阶段注入)
│   │   ├── SKILL.md                   # DNA分析 + 金手指设计工坊 + 改编方案格式
│   │   └── references/
│   │       └── golden_finger_patterns.md  # 6种创新手法素材库
│   ├── novel-imitate-generation/      # 仿写生成指南 (规划阶段也注入)
│   │   ├── SKILL.md                   # 写作技法 + 质量标准 + 正文格式
│   │   └── references/
│   │       └── writing_techniques.md  # 技法词表
│   └── novel-imitate-innovation/      # 仿写创新方法论 (agent按需读取)
│       └── SKILL.md                   # 角色偏离 + 金手指演化 + 情节重构
│
└── agent.py                           # create_imitate_agent() 入口
```

### 2.2 项目运行时目录

```
novels/仿写项目名/
├── .novel/
│   ├── config.yaml                    # 项目配置 (title, mode="imitate", source_file等)
│   ├── novel.db                       # SQLite主数据库 (WAL模式)
│   └── logs/
│       └── prompts-2026-02-28.md      # 每日prompt调试日志
├── source/                            # 源小说文件 (用户放置)
├── analysis/                          # 分析结果导出
├── chapters/                          # 生成的仿写章节
├── world/                             # 世界观设定
├── outline/                           # 大纲
└── output/                            # 最终输出 (Word/PDF)
```

---

## 三、核心数据模型

### 3.1 NovelConfig（项目配置）

存储在 `.novel/config.yaml`，项目创建时生成：

```python
@dataclass
class NovelConfig:
    title: str                          # 小说标题
    world_type: str                     # "original"|"onepiece"|"naruto"|"bleach"
    created_at: str                     # ISO时间戳
    author: str                         # 作者名
    description: str                    # 项目描述
    outline_model: str                  # 大纲模型
    writing_model: str                  # 写作模型
    chapter_word_count: tuple[int, int] # 目标字数范围 (3000, 8000)
    auto_summary: bool                  # 自动摘要
    progressive_mode: bool              # 渐进式场景确认
    mode: str                           # "original" | "imitate"
    source_file: str                    # 源文件路径 (仿写模式)
```

### 3.2 NovelProject（项目管理器）

```python
class NovelProject:
    path: Path                          # 项目根目录
    config_file: Path                   # .novel/config.yaml
    _config: NovelConfig | None         # 缓存的配置
    _state: NovelState | None           # 缓存的状态
    _db: NovelDatabase | None           # 懒加载的数据库实例

    @property
    def db() -> NovelDatabase           # 首次访问时创建
    @property
    def uses_sqlite() -> bool           # .novel/novel.db 是否存在
    @property
    def config() -> NovelConfig         # 加载或返回缓存
```

---

## 四、SQLite 数据库 Schema

数据库位于 `.novel/novel.db`，使用 WAL 模式支持并发读写。

### 4.1 imitate_source（源文元数据，单行）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK (固定=1) | |
| file_path | TEXT | 源文件路径 |
| total_chars | INTEGER | 总字符数 |
| total_chapters | INTEGER | 总章节数 |
| chapter_index | TEXT (JSON) | `[{id, title, char_offset, char_count}]` |

### 4.2 imitate_analysis（分析KV存储）

| 字段 | 类型 | 说明 |
|------|------|------|
| key | TEXT PK | 分析标识符 |
| content | TEXT | 分析内容 |
| updated_at | TEXT | 更新时间 |

常用 key 值：

| key | 内容 |
|-----|------|
| `source_overview` | 源文金手指全貌分析（用户确认后存入） |
| `dna_analysis` | 文风/节奏/技法 DNA |
| `adaptation_plan` | 逐章改编计划 **← 此key存在即触发阶段切换** |
| `character_mapping` | 源→新 角色映射表（含语言画像） |
| `power_system` | 金手指完整设定（创新手法+闭环+进阶路线） |
| `world_atmosphere` | 题材氛围 DNA 映射表 |

### 4.3 imitate_chapters（生成章节）

| 字段 | 类型 | 说明 |
|------|------|------|
| chapter | INTEGER PK | 章节号 |
| title | TEXT | 章节标题 |
| content | TEXT | 正文内容 |
| summary | TEXT | 80-200字摘要 |
| created_at | TEXT | 创建时间 |

### 4.4 imitate_character_evolution（角色演化轨迹）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER AI PK | |
| character_name | TEXT | 角色名 |
| chapter | INTEGER | 章节号 |
| changes | TEXT | 本章变化描述 |
| personality_shift | TEXT | 性格偏移 |
| relationship_changes | TEXT | 关系变化 |
| created_at | TEXT | |

### 4.5 imitate_power_evolution（金手指演化）

| 字段 | 类型 | 说明 |
|------|------|------|
| chapter | INTEGER PK | 章节号 |
| ability_unlocked | TEXT | 解锁的能力 |
| limitation_discovered | TEXT | 发现的限制 |
| usage_context | TEXT | 使用情境 |
| evolution_note | TEXT | 演化备注 |
| created_at | TEXT | |

### 4.6 imitate_creative_log（创意偏离记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER AI PK | |
| chapter | INTEGER | 章节号 |
| category | TEXT | `plot` / `character` / `golden_finger` / `setting` |
| source_original | TEXT | 源文原始内容 |
| adapted_version | TEXT | 改编后版本 |
| reason | TEXT | 偏离原因 |
| created_at | TEXT | |

### 4.7 imitate_skill_library（写作经验蒸馏）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER AI PK | |
| chapter | INTEGER | 来源章节 |
| skill_type | TEXT | `success_pattern` / `lesson_learned` |
| category | TEXT | `direction` / `writing` / `golden_finger` / `character` / `pacing` / `description` |
| content | TEXT | 一句话经验 |

### 4.8 memory（通用记忆表）

| 字段 | 类型 | 说明 |
|------|------|------|
| category | TEXT | `character` / `plot` / `foreshadow` / `setting` / `decision` / `summary` |
| key | TEXT | 标识符 |
| content | TEXT | 记忆内容 |
| updated_at | TEXT | |
| | | PRIMARY KEY (category, key) |

---

## 五、核心组件详解

### 5.1 源小说索引器（chunker.py）

负责将源小说文件变成可按章访问的结构：

```
源小说.txt
    │
    ▼
detect_encoding()
    │  尝试顺序: UTF-8 → GBK → GB2312 → BIG5 → GB18030 → chardet
    ▼
scan_chapter_boundaries()
    │  正则匹配章节标题:
    │  - "第X章/卷/回" (中文数字或阿拉伯数字)
    │  - "第X节" (仅当后跟空白/标点/行尾)
    │  - "Chapter N"
    │  - 数字前缀 "5 郊游"
    │  过滤: 行长度 ≤ 40 字符（排除正文误匹配）
    ▼
index_source_novel() → SourceIndex
    │
    ▼
SourceIndex {
    file_path, encoding, total_chars, total_bytes,
    chapters: [
        ChapterInfo {
            chapter_id: 1,
            title: "第一章 觉醒",
            char_offset: 0,        ← 字符偏移
            byte_offset: 0,        ← 字节偏移（用于 file.seek）
            char_count: 5200,
            byte_count: 15600
        },
        ...
    ]
}
```

读取方式（均使用 `file.seek()` 精确定位，不需要读取全文）：

| 函数 | 用途 |
|------|------|
| `load_chapter_text(path, index, chapter_id)` | 精读单章 |
| `load_chapter_range_text(path, index, start, end)` | 批量读多章 |
| `search_source_text(path, encoding, keyword)` | 关键词搜索，返回上下文片段 |

### 5.2 ImitateMemoryMiddleware（imitate_middleware.py）

每次 Agent 调用 LLM 之前，根据项目当前状态智能注入上下文到 system prompt。

```
Agent 准备调 LLM
      │
      ▼
wrap_model_call() / awrap_model_call()
      │
      ├─→ _build_auto_context()            ← 构建注入内容
      │       │
      │       ├── 项目元数据 (标题、模式、路径)
      │       ├── 已保存分析列表 + 已生成章节数
      │       │
      │       └── _detect_phase()           ← 核心：检查 DB 是否有 adaptation_plan
      │             │
      │             ├── 没有 → "planning" 阶段
      │             │     ├── 注入 novel-imitate-orchestrator/SKILL.md (完整)
      │             │     ├── 如果有 source_overview → 注入 references (金手指素材库)
      │             │     ├── 注入 novel-imitate-generation/SKILL.md (完整)
      │             │     │   + references/writing_techniques.md
      │             │     └── 注入完整工具速查表
      │             │
      │             └── 有 → "generation" 阶段
      │                   └── 只注入精简的 8 步生成流程 + 文件路径速查
      │                       (不注入完整 SKILL, 减少注意力稀释)
      │
      ├─→ append_to_system_message(request, context)
      │
      ├─→ _log_prompt(request)              ← 写入 .novel/logs/prompts-{date}.md
      │
      └─→ handler(modified_request)          ← 调用 LLM
```

**before_model() / abefore_model()** — 在调 LLM 前还执行源文消息压缩：

```
before_model(state)
      │
      └─→ _compact_source_messages(messages)
              扫描所有 ToolMessage
              如果是 read_source_chapter / read_source_range 的结果:
                保留最新一条完整内容
                旧的替换为 "[已阅读源文: 第N章 标题 (X字)]"
              → 大幅减少源文占用的 context 窗口
```

### 5.3 仿写工具集（imitate_tools.py）

Agent 可调用的 12 个工具（9 仿写 + 3 记忆）：

| 工具 | 签名 | 功能 | 阶段 |
|------|------|------|------|
| `index_source` | `(file_path: str)` | 扫描源文件，建立章节索引，存入 DB | 规划 |
| `read_source_chapter` | `(chapter: int)` | 精读单章，返回原文 + 元数据头 | 规划/生成 |
| `read_source_range` | `(start_chapter: int, end_chapter: int)` | 批量读多章 | 规划 |
| `search_source` | `(keywords: str, limit: int = 10)` | 关键词搜索源文 | 规划/生成 |
| `save_analysis` | `(key: str, content: str)` | 保存分析结果到 KV 表 | 规划 |
| `get_analysis` | `(key: str)` | 读取已保存的分析 | 规划/生成 |
| `get_generation_context` | `(chapter: int)` | 组装第 N 章的全部生成上下文 | 生成 |
| `save_chapter` | `(chapter: int, title: str, content: str, summary: str)` | 保存生成的章节 + 导出文件 | 生成 |
| `log_creative_choice` | `(chapter: int, category: str, source_original: str, adapted_version: str, reason: str)` | 记录创意偏离 | 生成 |
| `remember` | `(category: str, key: str, content: str)` | 存储记忆 | 任意 |
| `recall` | `(category: str = None, key: str = None)` | 检索记忆 | 任意 |
| `forget` | `(category: str, key: str)` | 删除记忆 | 任意 |

额外演化追踪工具（同文件中定义）：

| 工具 | 功能 |
|------|------|
| `evolve_character(name, chapter, changes, personality_shift, relationship_changes)` | 记录角色逐章变化 |
| `evolve_golden_finger(chapter, ability_unlocked, limitation_discovered, usage_context, evolution_note)` | 记录金手指演化 |
| `record_writing_skill(chapter, skill_type, category, content)` | 蒸馏用户反馈为经验 |

### 5.4 get_generation_context() — 生成上下文组装器

生成阶段最关键的工具，从 DB 中聚合本章写作所需的全部信息：

```
get_generation_context(chapter=N)
      │
      ├── 改编计划          ← imitate_analysis WHERE key='adaptation_plan'
      ├── 角色映射          ← imitate_analysis WHERE key='character_mapping'
      ├── 金手指设定        ← imitate_analysis WHERE key='power_system'
      ├── 题材氛围 DNA      ← imitate_analysis WHERE key='world_atmosphere'
      ├── 前一章摘要        ← imitate_chapters WHERE chapter = N-1
      ├── 角色演化轨迹      ← imitate_character_evolution (最近5章)
      ├── 金手指演化历程    ← imitate_power_evolution (全部)
      ├── 最近创意偏离      ← imitate_creative_log (最近3章)
      └── 写作经验          ← imitate_skill_library (全部)
           │
           ▼
      拼装为结构化 Markdown 返回给 Agent
```

### 5.5 ImitateHistoryBackend（imitate_history_backend.py）

只读虚拟文件后端，Agent 可通过 `read_file("/history/...")` 访问：

| 虚拟路径 | 渲染内容 |
|---------|---------|
| `/history/overview.md` | 所有章节列表 + 摘要 + 总字数 |
| `/history/chapter-{N}.md` | 第 N 章完整记录（正文 + 摘要 + 角色演化 + 金手指 + 偏离） |
| `/history/characters.md` | 全部角色的逐章演化轨迹 |
| `/history/golden-finger.md` | 金手指基础设计 + 演化时间线 |
| `/history/creative-log.md` | 全部创意偏离 + 分布统计 |
| `/history/skills.md` | 用户反馈蒸馏的写作经验库 |

所有写操作返回 "History backend is read-only." 错误。

### 5.6 CompositeBackend 虚拟文件路由

```
Agent 调 read_file(path) / write_file(path, content)
      │
      ▼
CompositeBackend 路由匹配
      │
      ├── path.startsWith("/skills/")
      │     → FilesystemBackend(内置 skills 目录)
      │     → 读取 SKILL.md / references/ 等
      │     → 例: read_file("/skills/novel-imitate-generation/SKILL.md")
      │
      ├── path.startsWith("/history/")
      │     → ImitateHistoryBackend (只读)
      │     → 从 SQLite 查询, 渲染为 Markdown 返回
      │     → 例: read_file("/history/characters.md")
      │
      └── 其他路径
            → FilesystemBackend(项目目录)
            → 真实文件读写
            → 例: read_file("/chapters/chapter-001.md")
```

---

## 六、Skill 技能文件详解

### 6.1 novel-imitate-orchestrator（规划阶段主技能）

**注入时机**：规划阶段（adaptation_plan 不存在时）每次调 LLM 都注入。

**核心内容**：

1. **工作流程**：`index_source → read_source_range → 源文金手指确认 → DNA分析 → 改编方案 → 用户选择 → 逐章生成`
2. **DNA 分析框架**：
   - 题材氛围 DNA（感官偏好、氛围密度、映射表）
   - 叙事视角与文风（人称、句式、转场）
   - 节奏模式（快慢节奏、爽点间距）
   - 金手指分析（燃料来源、变强方式、闭环逻辑、爽感类型）
3. **金手指设计工坊（四步创作法）**：
   - 第一步：用 6 种创新手法重构（载体替换/来源反转/副作用升格/维度降级/社会化改造/感官锚定）
   - 第二步：画闭环图（`[燃料] → [动作] → [能力提升] → [反哺]`）
   - 第三步：让燃料有趣、变强有画面、交互有策略
   - 第四步：写进阶路线（初/中/后期）
4. **改编方案格式**：S+/S/A-D 多方案展示，含对比表和多样性自检
5. **逐章生成 8 步流程**：精读 → 概述 → 上下文 → 改编方向 → 用户选择 → 写作 → 记录 → 反馈蒸馏

**引用素材**：`references/golden_finger_patterns.md`（仅在 source_overview 存在后加载）

### 6.2 novel-imitate-generation（生成指南技能）

**注入时机**：规划阶段完整注入；生成阶段不注入（Agent 按需通过 `read_file` 读取）。

**核心内容**：

1. **仿写 vs 抄袭的区别**：学源文的"怎么写"（技法），不抄源文的"写了什么"（内容）
2. **精读源文方法**：对照技法词表识别 5 类技法（开场与节奏/爽点/描写/人物/悬念与转场）
3. **章节类型→技法子集映射表**：战斗章/对话章/探索章/揭秘章/日常章各自的核心+辅助技法
4. **写作流程 4 步**：精读学技法 → 以改编计划为主线规划 → 逐场景原创写作 → 质量对照
5. **描写质量标准**：环境描写维度≥源文、人物刻画深度≥源文、金手指通过身体感受展现
6. **正文格式要求**：纯文本，禁止 Markdown，中文引号，段落空行分隔

**引用素材**：`references/writing_techniques.md`（技法词表）

### 6.3 novel-imitate-innovation（创新方法论）

**注入时机**：不主动注入，Agent 按需通过 `read_file("/skills/novel-imitate-innovation/SKILL.md")` 读取。

**核心内容**：

1. **角色偏离**：决策分叉、关系重构、金手指塑造性格
2. **金手指演化**：螺旋上升、限制驱动、情境触发
3. **情节偏离**：事件替换、因果链重构、情绪曲线保持
4. **创新度自检**：行为测试、金手指测试、换名测试

---

## 七、完整业务流程图

### 7.1 仿写全流程（宏观）

```
用户: deepagents novel init "我的仿写" --mode imitate --source "source/原著.txt"
  │
  ▼
[项目初始化]
  ├── 创建目录结构 (source/, chapters/, analysis/, ...)
  ├── config.yaml (mode=imitate, source_file=...)
  └── novel.db (空表)
  │
  ▼
用户: deepagents novel start "我的仿写"
  │
  ▼
[Agent 启动] ← create_imitate_agent()
  │
  ▼
╔══════════════════════════════════════════════════════════════╗
║              阶段一：规划 (Planning)                         ║
║  Middleware 检测: adaptation_plan 不存在                      ║
║  → 注入完整 Orchestrator + Generation SKILL                  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Step 1: 索引源文                                            ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ Agent 调 index_source("source/原著.txt")             │     ║
║  │ → chunker 编码检测 → 章节边界扫描                    │     ║
║  │ → 存入 imitate_source 表 (file_path, 章节索引JSON)   │     ║
║  │ → 返回: "共 N 章, M 万字"                            │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  Step 2: 批量阅读前几章                                      ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ Agent 调 read_source_range(1, 3) → 读前 3 章         │     ║
║  │ → chunker 按 byte_offset seek 读取                   │     ║
║  │ → 返回: 每章原文 + "=== 第N章 标题 (X字) ===" 头部   │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  Step 3: 源文金手指确认（只执行一次）                         ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ Agent 调 get_analysis("source_overview")             │     ║
║  │ → 不存在 → 向用户提问:                               │     ║
║  │   "请告诉我这本书的金手指/能力系统:                   │     ║
║  │    触发方式? 能力体系? 成长路线? 闭环结构?"           │     ║
║  │ → 用户回答                                           │     ║
║  │ → save_analysis("source_overview", 整理后的全貌分析)  │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  Step 4: DNA 深度分析                                        ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ Agent 分析源文:                                      │     ║
║  │ ├── 题材氛围 DNA (感官偏好、氛围密度、映射表)         │     ║
║  │ ├── 叙事视角与文风 (人称、句式节奏、转场方式)         │     ║
║  │ ├── 节奏模式 (快慢节奏、爽点间距、日常与高潮比例)     │     ║
║  │ └── 金手指分析 (燃料、变强方式、闭环逻辑、爽感类型)   │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  Step 5: 金手指设计工坊（四步创作法）                         ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ 第一步: 选 2-3 种创新手法重构金手指                   │     ║
║  │   (载体替换/来源反转/副作用升格/                      │     ║
║  │    维度降级/社会化改造/感官锚定)                      │     ║
║  │ 第二步: 画闭环图                                     │     ║
║  │   [燃料] → [动作] → [能力提升] → [反哺]              │     ║
║  │ 第三步: 燃料设计 + 变强画面对比 + 交互方式            │     ║
║  │ 第四步: 三级进阶路线 + 限制条件                       │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  Step 6: 展示改编方案                                        ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ S+ (首推): 同世界观 · 新维度 · 新金手指               │     ║
║  │ S:         同世界观 · 性别反转 · 新维度               │     ║
║  │ A-D:       跨题材改编 (2-4个)                        │     ║
║  │                                                      │     ║
║  │ 每个方案包含:                                        │     ║
║  │ ├── 新主角简介 + 与原著主角对比                       │     ║
║  │ ├── 金手指设计 (四步工坊完整产出)                     │     ║
║  │ ├── 场景变形 (≥3个, 每个3-5句场景短描)               │     ║
║  │ ├── 角色关系映射 (原著→新角色)                       │     ║
║  │ └── 外貌描写 (主角及核心角色)                        │     ║
║  │                                                      │     ║
║  │ 附带: 源文 vs 改编对比表 (燃料/变强/闭环/世界观)     │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
║  Step 7: 用户选择方案 → 保存分析结果                         ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │ save_analysis("adaptation_plan", ...)  ← 触发阶段切换│     ║
║  │ save_analysis("character_mapping", ...)              │     ║
║  │ save_analysis("power_system", ...)                   │     ║
║  │ save_analysis("world_atmosphere", ...)               │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  ⚡ 阶段自动切换                                             ║
║  Middleware._detect_phase() 发现 adaptation_plan 已存在       ║
║  → 下次调 LLM 时自动切换为 "generation" 模式                 ║
║  → 只注入精简的 8 步流程，不再注入完整 SKILL                 ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║              阶段二：逐章生成 (Generation)                    ║
║  Middleware 检测: adaptation_plan 存在                        ║
║  → 只注入精简流程                                            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ┌──── 每章循环 (N = 1, 2, 3, ...) ────────────────────┐    ║
║  │                                                      │    ║
║  │  Step 1: 精读源文                                    │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ read_source_chapter(N)                        │    │    ║
║  │  │ → 返回原文 + "=== 第N章 标题 (X字) ===" 头部  │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 2: 向用户输出源文概述                          │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ 使用技法词表中的具体术语:                     │    │    ║
║  │  │ ├── 情节脉络 (事件→功能)                      │    │    ║
║  │  │ ├── 章节类型 (战斗/对话/探索/揭秘/日常)       │    │    ║
║  │  │ ├── 开场技法 (先声夺人/悬念前置/...)          │    │    ║
║  │  │ ├── 节奏技法 (欲扬先抑/快进慢写/...)          │    │    ║
║  │  │ ├── 爽点标注 (@字数位置: 爽点类型)            │    │    ║
║  │  │ ├── 描写/人物/悬念技法                        │    │    ║
║  │  │ └── 情绪节奏曲线 (百分比分布)                 │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 3: 获取改编上下文                              │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ get_generation_context(N)                     │    │    ║
║  │  │ → 改编计划 + 角色映射 + 金手指设定            │    │    ║
║  │  │   + 氛围 DNA + 前文摘要                       │    │    ║
║  │  │   + 角色演化 + 金手指演化                     │    │    ║
║  │  │   + 创意偏离 + 写作经验                       │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 4: 提出 2-3 个改编方向                         │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ 每个方向包含:                                 │    │    ║
║  │  │ ├── 与原计划的关系 (沿用/微调/替换)           │    │    ║
║  │  │ ├── 场景拆分 (3-5场景, 含字数估算)            │    │    ║
║  │  │ ├── 技法应用计划                              │    │    ║
║  │  │ ├── 爽点设计                                  │    │    ║
║  │  │ ├── 角色表现                                  │    │    ║
║  │  │ ├── 金手指运用                                │    │    ║
║  │  │ └── 情绪曲线                                  │    │    ║
║  │  │ 方向间至少 2 个维度不同                       │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 5: 等待用户选择                                │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ ├── 直接选择: "方向B"                         │    │    ║
║  │  │ ├── 选择+补充: "方向A, 但金手指不要展现"      │    │    ║
║  │  │ ├── 混合选择: "场景用A, 金手指用B"            │    │    ║
║  │  │ └── 完全自定义: 用户描述自己的想法             │    │    ║
║  │  │ 用户补充优先级最高                            │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 6: 写作 + 保存                                 │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ 按选定方向写作 (纯中文文本, 禁止 Markdown)    │    │    ║
║  │  │ save_chapter(N, title, content, summary)      │    │    ║
║  │  │ → 存入 imitate_chapters 表                    │    │    ║
║  │  │ → 导出文件到 chapters/chapter-NNN.md          │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 7: 记录演化                                    │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ evolve_character(name, N, changes, ...)       │    │    ║
║  │  │ evolve_golden_finger(N, ability, limit, ...)  │    │    ║
║  │  │ log_creative_choice(N, category, src, new)    │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  │  Step 8: 用户反馈蒸馏                                │    ║
║  │  ┌──────────────────────────────────────────────┐    │    ║
║  │  │ 征集用户反馈 → record_writing_skill()         │    │    ║
║  │  │ 蒸馏为 1-3 条经验 (成功模式/经验教训)         │    │    ║
║  │  │ 用户说 "继续" → 跳过, 直接进入下一章          │    │    ║
║  │  └──────────────────────────────────────────────┘    │    ║
║  │                                                      │    ║
║  └──── 循环到下一章 ────────────────────────────────────┘    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

### 7.2 Agent 单轮调用的内部流程

```
用户发送消息
      │
      ▼
LangGraph Agent Loop
      │
      ├── [1] ImitateMemoryMiddleware.before_model(state)
      │         └── _compact_source_messages(): 压缩旧源文 ToolMessage
      │
      ├── [2] ImitateMemoryMiddleware.wrap_model_call(request)
      │         ├── _build_auto_context(): 构建状态感知的上下文
      │         ├── append_to_system_message(): 注入到 system prompt
      │         └── _log_prompt(): 写调试日志
      │
      ├── [3] LLM 推理 → 决定调哪些工具
      │
      ├── [4] 工具执行 (可能多次循环)
      │         ├── read_source_chapter() → 从文件 seek 读取
      │         ├── get_generation_context() → 从 DB 组装上下文
      │         ├── save_chapter() → 写 DB + 导出文件
      │         └── ...
      │
      ├── [5] 如果 tokens > 100k:
      │         └── SummarizationMiddleware: 压缩旧消息
      │
      └── [6] Agent 回复用户
```

---

## 八、数据流总结

```
源小说.txt
    │ index_source()
    ▼
imitate_source (DB)  ←→  chunker.py (按章 seek 读取)
    │                         │
    │ read_source_range()     │ read_source_chapter()
    ▼                         ▼
Agent 阅读 + 分析     ←──→  用户确认金手指
    │
    │ save_analysis()
    ▼
imitate_analysis (DB)
    ├── source_overview       ← 用户确认的金手指全貌
    ├── dna_analysis          ← 文风/节奏/技法分析
    ├── adaptation_plan       ← 逐章改编计划 (存入触发阶段切换)
    ├── character_mapping     ← 角色映射表
    ├── power_system          ← 金手指设定
    └── world_atmosphere      ← 氛围 DNA 映射表
         │
         │ get_generation_context(N)
         ▼
    组装上下文 → Agent 写作 → save_chapter(N)
         │                        │
         │                        ├── imitate_chapters (DB)
         │                        └── chapters/chapter-NNN.md (文件)
         │
         │ 演化记录
         ▼
    imitate_character_evolution  (角色逐章变化)
    imitate_power_evolution      (金手指演化时间线)
    imitate_creative_log         (创意偏离日志)
    imitate_skill_library        (用户反馈蒸馏经验)
         │
         │ read_file("/history/...")
         ▼
    ImitateHistoryBackend        (只读虚拟文件, 从 DB 渲染)
```

---

## 九、与原创模式的差异对比

| 维度 | 原创模式 | 仿写模式 |
|------|---------|---------|
| **阶段管理** | 6 阶段强制顺序 (brainstorm→revision) + `advance_phase()` 工具 | 无 Phase 锁，Agent 自由驱动；靠 `adaptation_plan` 是否存在自动切换 |
| **Middleware** | `NovelMemoryMiddleware` | `ImitateMemoryMiddleware` |
| **工具数** | 18 个记忆工具 + 文件系统工具 | 9 个仿写工具 + 3 个记忆工具 |
| **Hooks** | `NovelHooksRegistry` (pre/post 章节 hooks, 自动 checkpoint, 会话恢复) | 无 hooks |
| **数据来源** | 用户输入 + Agent 创作 | 源小说文件 + 用户确认 + Agent 改编 |
| **SKILL 注入** | orchestrator + 当前 phase 的 SKILL | 规划期完整注入；生成期精简摘要 |
| **额外后端** | 无 | `/history/` 虚拟文件后端 |
| **Agent 创建** | `create_novel_agent()` | `create_imitate_agent()` |

---

## 十、关键设计决策

| 决策 | 理由 |
|------|------|
| **无 Phase 锁** | 仿写是 Agent 驱动的自由流程，不需要 6 阶段的强制顺序 |
| **阶段检测靠 DB** | 简单可靠，`adaptation_plan` 是否存在即为分界线 |
| **规划阶段注入完整 SKILL，生成阶段只注入摘要** | 避免注意力稀释——生成时 Agent 不需要重读 DNA 分析方法论 |
| **源文 ToolMessage 自动压缩** | 源文占 context 极大，旧的源文结果压缩为一行摘要 |
| **SQLite WAL 模式** | 支持 Agent 并发读写，不会锁表 |
| **虚拟 /history/ 后端** | Agent 可通过标准 `read_file` 访问结构化历史，无需专门工具 |
| **金手指设计四步法 + 6 种创新手法** | 防止 Agent 做简单"换皮"，强制结构化创新 |
| **每章 8 步流程 (分析→协商→写作)** | 确保每章都与用户对齐方向，不闷头写 |
| **经验蒸馏 (record_writing_skill)** | 跨章学习用户偏好，越写越符合用户口味 |
| **只给仿写 Agent 3 个记忆工具** | 原创模式的 18 个工具（角色管理/伏笔/阶段推进）对仿写无意义，减少 context 消耗 |
