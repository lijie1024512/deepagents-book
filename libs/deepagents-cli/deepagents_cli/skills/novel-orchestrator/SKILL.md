---
name: novel-orchestrator
description: 小说创作总调度器。管理创作阶段流转，确保按流程推进。常驻加载。
---

# 小说创作总调度器

## 阶段流程

| # | 代号 | 核心任务 | 产出 | 完成标志 |
|---|------|---------|------|---------|
| 1 | brainstorm | 类型、吸引力、参考 | 用户确认 | 用户选择 |
| 2 | engine | 创意引擎（核心矛盾） | engine.md | 用户选定方案 |
| 3 | character | 主角设定、矛盾、弧光 | 角色卡 | 用户确认 |
| 4 | outline | 弧线+章节大纲 | outline.md | 用户确认 |
| 5 | writing | 前3章精磨+滚动生成 | chapters/*.md | 用户确认 |
| 6 | revision | 多维度诊断优化 | 修订后文件 | 用户满意 |

## 流转规则

- 必须等用户确认当前阶段产出后，才能 `advance_phase()` 推进
- 禁止跳阶段（除非用户明确要求 skip）
- 用户可随时回退：`advance_phase(target, reason, back=True)`

## 输出规则

- 选项每项一行、≤25字，末尾提示"回复字母即可"
- 回复简洁：选项≤10行，确认≤2句，总结≤5行
- 提供选择而非开放问题，主动给2-3个方案

## 项目文件

```
novels/项目名/
├── engine.md        ← 引擎设计（灵魂文件）
├── outline.md       ← 大纲（滚动更新）
├── chapters/*.md    ← 正文
├── style_notes.md   ← 风格参考
└── progress.md      ← 进度+反馈
```
