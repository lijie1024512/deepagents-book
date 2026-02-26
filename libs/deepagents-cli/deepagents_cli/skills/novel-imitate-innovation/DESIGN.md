# 仿写模式上下文优化设计文档

## 1. 问题诊断

### 1.1 优化前的上下文架构

```
优化前（生成阶段，第 10 章）:

System Prompt            ~3,700 tokens  ← 每轮固定注入
├─ 基础 prompt            ~600 tokens    角色定义/原则/4步流程/禁止列表/格式要求
└─ Middleware 注入         ~3,100 tokens
   ├─ 项目元数据            ~100 tokens
   ├─ generation SKILL.md  ~2,000 tokens  ← 整段写作指南每轮塞入
   ├─ 工具流程+禁止列表      ~500 tokens   ← 与 system prompt 重复
   └─ 格式要求+仿写原则      ~500 tokens   ← 与 system prompt 重复

get_generation_context   ~8-10K tokens
├─ 改编计划                variable       可能是全文截断，非精确提取
├─ 全量角色映射             ~3,000 截断     不区分本章涉及谁
├─ 全量金手指设计           variable       静态，保存后不再更新
├─ 全量氛围DNA             variable       不压缩
└─ 最近3章摘要             variable       无全局摘要，线性增长

对话历史                  ~40K tokens     10 章累积，无 offload
──────────────────────────────────────
总计                      ~55K tokens
```

### 1.2 四个核心问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | **System Prompt 职责混乱** | 行为约束、领域知识（写作指南）、工具说明混在一起，每轮注入 ~3,700 tokens |
| 2 | **上下文全量灌入** | 角色映射、金手指、氛围不区分本章是否需要，全量截断而非智能提取 |
| 3 | **创新无追踪** | 金手指保存一次不再演化，角色映射固定不更新，无创意偏离记录 |
| 4 | **辅助信息 > 当前任务** | 写作指南（2,000 tokens）+ 工具说明（500 tokens）比改编计划本身占比更大 |

### 1.3 注意力稀释的具体表现

```
优化前 System Prompt 中，按 token 占比:

写作指南（generation SKILL.md）  54%  ← 占比最大，但只是方法论
工具流程 + 禁止列表             14%  ← 重复了 system prompt 已有的内容
格式要求 + 仿写原则             14%  ← 同上
项目元数据                      3%
改编计划引用（在 tool return 中）  0%  ← 最重要的内容不在 system prompt

问题: LLM 的注意力大部分在"怎么写"（方法论），而不是"写什么"（改编计划）。
```

---

## 2. 设计原则

### 2.1 借鉴 Claude Code 的分层上下文模型

Claude Code（本项目的 deepagents 框架）对上下文管理有一套成熟的分层设计:

```
┌─────────────────────────────────────────────────────────────┐
│ System Prompt — 行为常量                                      │
│   "你是什么、核心原则是什么、流程几步"                            │
│   特征: 不随任务变化、每轮固定、尽量精简                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Tool Description — 工具使用说明                                │
│   "这个工具怎么用、什么时候用、返回什么"                          │
│   特征: 随工具注册、agent 决定调用时自然会看到                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Skill（按需读取）— 领域方法论                                   │
│   "怎么分析DNA、怎么设计金手指、怎么保证创新"                      │
│   特征: System Prompt 只放名字+路径，agent 需要时 read_file 读取   │
│         读取后进入对话历史，可被 summarization 压缩                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Tool Return — 当前任务的实际数据                                │
│   "本章改编计划、涉及角色、金手指状态、前文脉络、创新提示"            │
│   特征: 每次调用动态生成、智能提取、只包含当前章需要的内容            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Database（持久存储）— 跨章节状态                                │
│   "角色演化轨迹、金手指演化历程、创意偏离日志、章节摘要"             │
│   特征: 持久化到 SQLite，在 tool return 中按需注入                │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**: 每一层只放属于该层的内容。方法论不应该在 System Prompt，实际数据不应该在 Skill。

### 2.2 上下文比例原则

```
当前任务内容（改编计划 + 源文技法）  ≥ 50%    ← 主角
前文脉络（滑动窗口摘要）            ~20%     ← 配角
设定/角色参考（智能提取）            ~15%     ← 道具
行为约束 + 用户偏好                 ~15%     ← 舞台规则
```

改编计划始终应该是上下文中**占比最大、位置最前**的内容。

### 2.3 Skill 与 Tool 的互补关系

| 层 | 职责 | 仿写场景 | 加载时机 |
|---|---|---|---|
| **Skill** | 创作方法论、思维框架 | "如何学习源文技法"、"如何让角色偏离"、"如何让金手指演化" | agent 按需 read_file |
| **Tool** | 执行动作、读写状态 | `read_source_chapter`、`save_chapter`、`evolve_character` | 随时可调用 |
| **Tool Description** | 该工具的使用指南 | "save_chapter 的格式要求"、"evolve_character 记录什么" | 随工具注册 |
| **System Prompt** | 身份、原则、流程 | "你是仿写作家、5步流程、核心原则" | 每轮固定 |

**之前的错误**: 把 Skill 内容（generation SKILL.md 全文）直接塞进 System Prompt，
让 System Prompt 承担了方法论教学的职责，违反了分层原则。

---

## 3. 架构改动

### 3.1 System Prompt 精简

**优化前** (~3,700 tokens，生成阶段):

```
_get_imitate_system_prompt()       ~600 tokens
  ├─ 角色定义
  ├─ 核心原则（4条）
  ├─ 4步流程（含工具调用示例）
  ├─ 严禁操作列表
  └─ 文件操作说明

ImitateMemoryMiddleware 注入        ~3,100 tokens
  ├─ 项目元数据                      ~100
  ├─ generation SKILL.md 全文         ~2,000  ← 最大浪费
  ├─ 工具流程（3步）                   ~200
  ├─ 正文格式要求                     ~200
  ├─ 仿写核心原则（重复）              ~150
  └─ 严禁操作列表（重复）              ~150
```

**优化后** (~1,100 tokens，生成阶段):

```
_get_imitate_system_prompt()       ~700 tokens
  ├─ 角色定义（精简）
  ├─ 核心原则（3条）
  ├─ 5步流程（含创新记录步骤）
  ├─ 正文格式（1行）
  ├─ 技能目录（2个路径）              ← 只放路径，不放内容
  └─ 文件操作说明

ImitateMemoryMiddleware 注入        ~400 tokens
  ├─ 项目元数据                      ~100
  ├─ 5步流程（精简）                   ~200  ← 行为约束，不含方法论
  ├─ 正文格式（1行）                   ~30
  └─ 技能目录（2个路径）               ~70   ← 只放路径
```

**节省: 3,700 → 1,100 tokens（减少 70%）**

### 3.2 get_generation_context 重写

**优化前** — 静态全量灌入:

```python
# 旧实现
def get_generation_context(chapter):
    parts = []
    parts.append(adaptation_plan[chapter] or plan[:4000])   # 可能截断全文
    parts.append(character_mapping[:3000])                  # 全量截断
    parts.append(power_system)                              # 全量，从不更新
    parts.append(world_atmosphere)                          # 全量
    parts.append(last_3_chapter_summaries)                  # 固定3章
    return "\n".join(parts)
```

**优化后** — 智能提取 + 活的创新状态:

```python
# 新实现
def get_generation_context(chapter):
    parts = []

    # ① 本章改编计划 — 精确提取，最高优先级
    parts.append(extract_chapter_plan(chapter))

    # ② 本章涉及角色 — 只提取章节计划中提到的角色
    #    + 角色演化轨迹（从 imitate_character_evolution 表）
    parts.append(extract_relevant_characters(chapter_plan))
    parts.append(character_evolution_history)       # 🆕 活的

    # ③ 金手指：基础设计(压缩) + 演化历程
    #    从 imitate_power_evolution 表获取逐章演化记录
    parts.append(power_base_design[:1500])          # 压缩到 1500 字符
    parts.append(power_evolution_history)            # 🆕 活的

    # ④ 氛围速查 — 压缩到 1000 字符
    parts.append(world_atmosphere[:1000])

    # ⑤ 前文脉络 — 滑动窗口（全局脉络 + 近3章详细）
    parts.append(sliding_window_summary(chapter))   # 🆕 不再线性增长

    # ⑥ 创新提示 — 基于 imitate_creative_log 分析偏离模式
    parts.append(innovation_prompt(chapter))         # 🆕 动态生成

    return "\n".join(parts)
```

### 3.3 新增数据库表

```sql
-- 角色演化追踪（每章可更新，按角色+章节复合主键）
CREATE TABLE imitate_character_evolution (
    character_name TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    changes TEXT NOT NULL,            -- "首次觉醒金手指，性格从怯懦转为好奇"
    personality_shift TEXT DEFAULT '', -- "从被动→主动探索"
    relationship_changes TEXT DEFAULT '', -- "与导师关系从警惕→信任"
    PRIMARY KEY (character_name, chapter)
);

-- 金手指逐章演化（每章一条记录）
CREATE TABLE imitate_power_evolution (
    chapter INTEGER PRIMARY KEY,
    ability_unlocked TEXT DEFAULT '',     -- "发现可以感知金属内部结构"
    limitation_discovered TEXT DEFAULT '', -- "使用后极度饥饿，持续30分钟"
    usage_context TEXT DEFAULT '',        -- "被迫在生死危机中使用"
    evolution_note TEXT DEFAULT ''        -- "比第1章的被动感知变为主动探测"
);

-- 创意偏离日志（每章可有多条）
CREATE TABLE imitate_creative_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    category TEXT NOT NULL,          -- "plot" / "character" / "golden_finger" / "setting"
    source_original TEXT DEFAULT '',  -- "源文：格斗比赛展示能力"
    adapted_version TEXT DEFAULT '',  -- "改编：实验事故被迫使用能力"
    reason TEXT DEFAULT ''           -- "更符合改编角色的被动性格"
);
```

### 3.4 新增工具

| 工具 | 参数 | 用途 |
|------|------|------|
| `evolve_character` | character_name, chapter, changes, personality_shift, relationship_changes | 记录角色逐章成长 |
| `evolve_golden_finger` | chapter, ability_unlocked, limitation_discovered, usage_context, evolution_note | 记录金手指逐章演化 |
| `log_creative_choice` | chapter, category, source_original, adapted_version, reason | 记录创意偏离决策 |

这三个工具写入的数据会在下一章的 `get_generation_context` 中**自动注入**，形成创新滚雪球效应。

### 3.5 新增 Skill: novel-imitate-innovation

```
skills/novel-imitate-innovation/SKILL.md (106 行，~2,200 字符)
├─ 一、角色偏离方法论（决策分叉、关系重构、金手指塑造性格）
├─ 二、金手指演化模式（螺旋上升、限制驱动、情境触发）
├─ 三、情节偏离策略（事件替换、因果链重构、情绪曲线保持）
└─ 四、创新度自检（行为测试、金手指测试、换名测试）
```

这个 Skill 不会自动注入 System Prompt，而是 agent 在需要创意指导时通过
`read_file("/skills/novel-imitate-innovation/SKILL.md")` 按需读取。

---

## 4. 上下文流转全图

### 4.1 规划阶段

```
用户消息: "帮我分析这本源小说的DNA，提出改编方案"
    │
    ▼
System Prompt (~1,100 tokens)
├─ 身份 + 核心原则 + 5步流程
├─ 技能目录（2个路径）
└─ 文件操作说明
    │
    ▼ ImitateMemoryMiddleware.wrap_model_call()
    │  _detect_phase() → "planning"（adaptation_plan 不存在）
    │
    ▼ 追加到 System Prompt:
├─ 项目元数据 (~100 tokens)
├─ 【已保存分析】/ 【已生成章节】
├─ orchestrator SKILL.md 全文 (~3,000 tokens)    ← 规划阶段需要完整方法论
├─ golden_finger_patterns.md 参考 (~1,500 tokens) ← source_overview 存在后加载
├─ generation SKILL.md 全文 (~2,000 tokens)       ← 规划阶段也预览生成指南
└─ 工具速查 (~200 tokens)
    │
    ▼ 总计: ~8,000 tokens（规划阶段需要丰富上下文来做决策）
    │
    ▼ LLM 执行:
    │  index_source → read_source_range(1,3) → 向用户确认金手指
    │  → save_analysis("source_overview") → DNA 分析
    │  → 提出 S+/S/A-D 改编方案 → 用户选择
    │  → save_analysis("adaptation_plan" + "character_mapping"
    │                + "power_system" + "world_atmosphere")
    │
    ▼ 数据库状态变化: adaptation_plan 存在 → 下次 _detect_phase() 返回 "generation"
```

### 4.2 生成阶段

```
用户消息: "生成第5章"
    │
    ▼
System Prompt (~1,100 tokens)                     ← 精简：身份+原则+5步+技能目录
    │
    ▼ ImitateMemoryMiddleware.wrap_model_call()
    │  _detect_phase() → "generation"
    │
    ▼ 追加到 System Prompt (~400 tokens):           ← 不再塞入 SKILL 全文
├─ 项目元数据
├─ 5步流程（精简版）
├─ 正文格式（1行）
└─ 技能目录路径（2行）
    │
    ▼ System Prompt 总计: ~1,500 tokens             ← 优化前 3,700，减少 60%
    │
    ▼ LLM 执行 Step 1:
    │  read_source_chapter(5)
    │  → 返回源文第5章 + 仿写铁律提醒 (~3K tokens)
    │
    ▼ LLM 执行 Step 2:
    │  get_generation_context(5)
    │  → 返回 (~4-5K tokens):
    │    ┌─ ## 本章改编计划（核心目标）         ← 精确提取，不是全文截断
    │    ├─ ## 本章涉及角色                   ← 只含本章提到的角色
    │    │  └─ ### 角色演化轨迹                ← 🆕 活的：第1-4章成长记录
    │    ├─ ## 金手指
    │    │  ├─ ### 基础设计（压缩到1500字符）
    │    │  └─ ### 演化历程                    ← 🆕 活的：逐章能力/限制/情境
    │    ├─ ## 氛围速查（压缩到1000字符）
    │    ├─ ## 前文脉络
    │    │  ├─ 【全局脉络】第1章→第2章→...      ← 🆕 滑动窗口，不线性增长
    │    │  └─ 【近章摘要】第3/4章详细摘要
    │    └─ ## 创新提示                        ← 🆕 基于偏离模式动态生成
    │       "前几章创意偏离分布：情节60%、角色30%、金手指10%"
    │       "建议本章加强：设定方面的创新"
    │       "金手指已经2章没有演化，考虑展示新面向"
    │
    ▼ LLM 执行 Step 3: 原创写作
    │
    ▼ LLM 执行 Step 4:
    │  save_chapter(5, content="...", summary="...", title="...")
    │  → 返回提示: "接下来请记录本章创新"
    │
    ▼ LLM 执行 Step 5 — 创新记录:                    ← 🆕
    │  evolve_character("莱恩", 5, "首次主动使用金手指保护他人",
    │                   personality_shift="从被动→主动",
    │                   relationship_changes="与导师从警惕→信任")
    │  evolve_golden_finger(5, ability_unlocked="主动探测模式",
    │                       limitation_discovered="探测范围仅3米",
    │                       usage_context="生死危机中被迫突破")
    │  log_creative_choice(5, "plot", "源文格斗比赛",
    │                      "改编实验事故", "更符合科研世界观")
    │
    ▼ LLM 向用户汇报: "第5章完成，4200字。角色和金手指都有重要演化..."
    │
    ▼ 数据库状态更新:
       imitate_character_evolution: +1 行
       imitate_power_evolution: +1 行
       imitate_creative_log: +1 行
       → 下一章 get_generation_context(6) 会自动包含这些演化数据
```

---

## 5. Token 预算对比

### 5.1 生成阶段单次调用

| 组件 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| System Prompt | ~3,700 | ~1,100 | -70% |
| Middleware 追加 | (含在上面) | ~400 | (分离) |
| **System Prompt 总计** | **~3,700** | **~1,500** | **-60%** |
| read_source_chapter 返回 | ~3,000 | ~3,000 | 不变 |
| get_generation_context 返回 | ~8-10K | ~4-5K | -50% |
| 对话历史（第10章时） | ~40K | ~15K | -63%（summarization） |
| **总计（第10章）** | **~55K** | **~24K** | **-56%** |

### 5.2 各组件 token 占比变化

```
优化前（第10章，~55K tokens）:
┌──────────────────────────────────────┐
│ 对话历史          73%  ████████████████████████████████████│
│ get_gen_context   16%  ████████                            │
│ System Prompt      7%  ███                                 │
│ 源文章节           5%  ██                                  │
└──────────────────────────────────────┘
问题: 改编计划（核心目标）只占 get_gen_context 的一部分，总占比 <5%

优化后（第10章，~24K tokens）:
┌──────────────────────────────────────┐
│ 对话历史          42%  █████████████████████               │
│ get_gen_context   21%  ██████████                          │
│ 源文章节          13%  ██████                              │
│ System Prompt      6%  ███                                 │
│ 创新记录工具返回    4%  ██                                  │
│ ─其中─                                                     │
│ 改编计划占总比     ~12%  ██████         ← 从 <5% 升至 12%   │
└──────────────────────────────────────┘
改编计划成为占比最大的单一内容块。
```

---

## 6. 创新追踪的滚雪球效应

### 6.1 数据流

```
第1章写完 →
  evolve_character("莱恩", 1, "觉醒")
  evolve_golden_finger(1, "基础感知")
  log_creative_choice(1, "setting", "魔法学院", "科研实验室")
       │
       ▼ 存入 SQLite
       │
第2章 get_generation_context(2) →
  ## 本章涉及角色
    莱恩
    ### 角色演化轨迹
    **莱恩**:
      - 第1章: 觉醒
  ## 金手指
    ### 演化历程
    - 第1章: 【能力】基础感知
  ## 创新提示
    前几章创意偏离分布: 设定100%
    建议本章加强: 情节、角色、金手指方面的创新
       │
       ▼ LLM 据此做出更有针对性的创新
       │
第2章写完 →
  evolve_character("莱恩", 2, "首次与对手冲突，展现果断一面")
  evolve_golden_finger(2, "探测范围扩大到5米", "高强度使用后头痛")
  log_creative_choice(2, "character", "源文对手嫉妒心驱动", "改编对手路线之争")
       │
       ▼
第3章 get_generation_context(3) →
  ## 角色演化轨迹
  **莱恩**:
    - 第1章: 觉醒
    - 第2章: 首次与对手冲突，展现果断一面
      性格偏移: 从怯懦→果断
  ## 金手指演化历程
    - 第1章: 【能力】基础感知
    - 第2章: 【能力】探测范围扩大 【限制】高强度使用后头痛
    当前状态（第2章后）: 已解锁能力 2次演化
  ## 创新提示
    前几章创意偏离分布: 设定50%、角色50%
    建议本章加强: 情节、金手指方面的创新
```

**效果**: 每章的创新决策会影响下一章的上下文，形成**有方向的创新积累**，
而不是每章独立地"跟着改编计划机械执行"。

### 6.2 创新提示的生成逻辑

`_build_innovation_prompt()` 函数分析 `imitate_creative_log` 表，生成三类提示:

1. **偏离分布分析**: 统计最近5章的 category 分布（情节/角色/金手指/设定各占比），
   找出占比 <15% 的类别建议加强。
2. **金手指新鲜度**: 检查 `imitate_power_evolution` 最近记录的章节号，
   如果距当前章 ≥3 章没有演化，提示考虑展示新面向。
3. **角色活跃度**: 展示近期有演化记录的角色名单。

---

## 7. Skill 渐进式加载策略

### 7.1 旧模式 vs 新模式

```
旧模式（ImitateMemoryMiddleware 直接塞入）:
  每次 LLM 调用 → System Prompt 包含 generation SKILL.md 全文（~2,000 tokens）
  问题: 每轮都占用上下文，即使 agent 不需要写作指南

新模式（渐进式加载）:
  System Prompt: "写作技法 → read_file('/skills/novel-imitate-generation/SKILL.md')"
  agent 需要时 → 调用 read_file → Skill 内容进入对话历史
  优势:
    - System Prompt 只多 ~70 tokens（2个路径）
    - Skill 内容作为 tool_result 进入对话历史
    - 历史消息可被 SummarizationMiddleware 压缩
    - agent 有选择权: 第1章可能读完整指南，第10章已经内化了就不读
```

### 7.2 何时读哪个 Skill

| 场景 | 推荐读取的 Skill | 触发条件 |
|------|-----------------|----------|
| 首次生成章节 | `novel-imitate-generation` | agent 判断需要写作指南 |
| 创新度不足 | `novel-imitate-innovation` | 创新提示建议加强某方面 |
| 角色写不出差异 | `novel-imitate-innovation` §一 | agent 感觉角色太像源角色 |
| 金手指没有变化 | `novel-imitate-innovation` §二 | 连续几章金手指无演化 |

---

## 8. 滑动窗口摘要策略

### 8.1 实现: `_build_sliding_summary()`

```
章节 1-4（少量前文）:
  直接列出所有前章摘要
  - 第1章《觉醒》: 莱恩在实验室中意外觉醒金手指...
  - 第2章《冲突》: 首次与对手交锋...
  - 第3章《突破》: 金手指被迫进化...

章节 5+（大量前文）:
  【全局脉络】第1章(觉醒...) → 第2章(冲突...) → 第3章(突破...) → 第4章(转折...)

  【近章摘要】
  - 第5章《探索》: 莱恩开始主动探索金手指的新用法...
  - 第6章《危机》: 实验室爆炸事件，被迫暴露能力...
  - 第7章《选择》: 面临留在实验室还是加入特战队的抉择...
```

### 8.2 token 增长对比

```
旧策略（最近3章固定窗口）:
  第5章:  3条摘要 ~300 tokens
  第10章: 3条摘要 ~300 tokens   ← 信息丢失: 第1-6章不可见
  第50章: 3条摘要 ~300 tokens   ← 信息丢失: 第1-46章不可见

新策略（滑动窗口 + 全局脉络）:
  第5章:  全局(2条压缩) + 近章(3条详细) ~400 tokens
  第10章: 全局(7条压缩) + 近章(3条详细) ~500 tokens
  第50章: 全局(47条压缩) + 近章(3条详细) ~800 tokens  ← 增长缓慢，且保留全局脉络
```

---

## 9. 与原有架构的兼容性

### 9.1 向后兼容

- 新增的 3 张 DB 表使用 `CREATE TABLE IF NOT EXISTS`，不影响已有表
- 新增的 3 个工具追加到 `get_all_imitate_tools()` 返回列表末尾
- `save_chapter` 的返回消息变更不影响功能，只是提示 agent 记录创新
- 规划阶段的行为完全不变（orchestrator SKILL 仍然全文注入）
- 老项目（无 innovation 数据）: `get_generation_context` 的新代码在查询为空时自然跳过

### 9.2 不兼容变更

- 生成阶段 System Prompt 不再包含 generation SKILL.md 全文
  → agent 首次生成时可能需要主动 `read_file` 获取写作指南
  → 这是**设计意图**: 让 agent 有选择权，而非被动接收

---

## 10. 文件变更清单

| 文件 | 改动类型 | 内容 |
|------|---------|------|
| `novel/imitate_tools.py` | 修改 | +3 DB 表 schema, +3 新工具, 重写 `get_generation_context`, +3 辅助函数, 修改 `save_chapter` 返回, 更新 `get_all_imitate_tools` |
| `novel/imitate_middleware.py` | 修改 | 生成阶段: 去掉 SKILL 全文注入, 改为精简行为约束 + 技能目录; 规划阶段: 工具速查新增创新追踪工具 |
| `agent.py` | 修改 | `_get_imitate_system_prompt()`: 4步→5步流程, 新增创新工具引用, 新增技能目录, 精简核心原则 |
| `skills/novel-imitate-innovation/SKILL.md` | 新增 | 创新方法论 Skill（角色偏离/金手指演化/情节重构/创新度自检） |
