# 小说创作 CLI 使用指南

## 安装与运行

### 方式一：使用 `uv run`（推荐开发时使用）

无需安装，直接从项目目录运行：

```bash
# 进入 CLI 项目目录
cd /home/lijie/test/deepagents-book/libs/deepagents-cli

# 运行命令
uv run deepagents novel <command>
```

### 方式二：安装到系统（推荐日常使用）

```bash
# 进入 CLI 项目目录
cd /home/lijie/test/deepagents-book/libs/deepagents-cli

# 安装到系统（开发模式）
uv pip install -e .

# 之后可以在任意位置直接使用
deepagents novel <command>
```

---

## 命令列表

| 命令 | 说明 |
|-----|------|
| `deepagents novel init <标题>` | 创建新的小说项目 |
| `deepagents novel list` | 列出所有小说项目 |
| `deepagents novel status` | 查看当前项目状态 |
| `deepagents novel start` | 启动对话式创作会话 |

---

## 快速开始

### 1. 创建新项目

```bash
# 创建一个海贼王同人小说项目
deepagents novel init "我的海贼小说" --world onepiece

# 创建一个火影同人小说项目
deepagents novel init "我的火影小说" --world naruto

# 创建一个原创小说项目
deepagents novel init "我的原创小说" --world original
```

项目会创建在 `~/novels/<项目名>/` 目录下。

### 2. 查看项目列表

```bash
deepagents novel list
```

输出示例：
```
小说项目列表:

  🆕 我的海贼小说
     世界观: onepiece
     进度: 大纲 0/? 章, 正文 0/? 章
     位置: /home/lijie/novels/我的海贼小说
```

### 3. 启动创作会话

```bash
# 进入项目目录
cd ~/novels/我的海贼小说

# 启动对话式创作（自动模式）
deepagents novel start

# 或指定项目名（无需进入目录）
deepagents novel start 我的海贼小说
```

### 4. 指定创作模式

```bash
# 专注大纲创作
deepagents novel start --mode outline

# 专注正文写作
deepagents novel start --mode write

# 专注修改优化
deepagents novel start --mode revise
```

---

## 项目结构

创建项目后，会自动生成以下目录结构：

```
~/novels/我的海贼小说/
├── .novel/              # 项目配置和状态
│   ├── config.yaml      # 项目配置
│   ├── state.yaml       # 当前进度状态
│   └── checkpoints/     # 状态检查点
├── world/               # 世界观设定
│   ├── knowledge-base.md
│   └── characters/      # 角色档案
├── outline/             # 大纲
│   └── story-framework.md
├── chapters/            # 正文章节
└── output/              # 导出文件
```

---

## 对话式创作流程

启动 `deepagents novel start` 后，进入对话式创作模式：

### 新项目流程

```
1. Agent 会引导你确定主角设定
   - 提供选择题：性格类型、金手指类型、起点等

2. 确定故事框架
   - 核心冲突、主要目标、第一卷概述

3. 生成章节大纲
   - 渐进式生成，每步确认后再继续

4. 撰写正文
   - 逐场景生成，每个场景确认后再继续
```

### 继续创作流程

```
1. Agent 会读取项目状态，显示当前进度
2. 根据进度提供选项：
   A. 续写大纲
   B. 继续写正文
   C. 优化已有内容
   D. 查看项目状态
```

---

## 常用操作

### 查看项目状态

```bash
# 在项目目录内
deepagents novel status

# 或指定项目名
deepagents novel status 我的海贼小说
```

### 退出会话

在对话界面中：
- 按 `Ctrl+C` 退出
- 或输入 `/quit`

### 查看帮助

```bash
# 查看总体帮助
deepagents novel --help

# 查看具体命令帮助
deepagents novel init --help
deepagents novel start --help
```

---

## 环境要求

- Python 3.11+
- 需要配置 API 密钥（如 `ANTHROPIC_API_KEY`）

### 配置 API 密钥

```bash
# 方式一：环境变量
export ANTHROPIC_API_KEY="your-api-key"

# 方式二：.env 文件
echo 'ANTHROPIC_API_KEY=your-api-key' >> ~/.env
```

---

## 故障排除

### 问题：`deepagents: command not found`

**原因**：CLI 未安装到系统 PATH

**解决**：
```bash
cd /home/lijie/test/deepagents-book/libs/deepagents-cli
uv pip install -e .
```

### 问题：创建会话失败

**原因**：API 密钥未配置或无效

**解决**：
```bash
# 检查密钥是否配置
echo $ANTHROPIC_API_KEY

# 如果为空，设置密钥
export ANTHROPIC_API_KEY="your-api-key"
```

### 问题：找不到项目

**原因**：不在项目目录内，且未指定项目名

**解决**：
```bash
# 方式一：进入项目目录
cd ~/novels/我的海贼小说
deepagents novel start

# 方式二：指定项目名
deepagents novel start 我的海贼小说
```
