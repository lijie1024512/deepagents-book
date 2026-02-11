# DeepAgents CLI 命令速查

> 在 `libs/deepagents-cli/` 目录下执行

---

## 对话

```bash
# 启动对话
uv run deepagents

# 带初始提示启动
uv run deepagents -m "帮我写个Python爬虫"

# 恢复上次对话
uv run deepagents -r

# 恢复指定对话
uv run deepagents -r <会话ID>

# 指定模型
uv run deepagents --model gpt-5-mini

# 自动批准所有工具调用（不逐个确认）
uv run deepagents --auto-approve

# 使用独立记忆空间的Agent
uv run deepagents --agent mybot

# Windows下使用纯终端模式
uv run deepagents --terminal
```

---

## 会话历史

```bash
# 查看所有会话记录
uv run deepagents threads list

# 只看某个Agent的会话
uv run deepagents threads list --agent mybot

# 删除一条会话记录
uv run deepagents threads delete <会话ID>

# 删除某本小说的对话历史
uv run deepagents threads delete novel-海贼王之只手遮天

# 删除某个仿写项目的对话历史
uv run deepagents threads delete imitate-神秘之旅改编
```

**会话ID说明：**

`threads list` 会列出所有会话的 ID，直接从 ID 就能看出是哪本小说：

| 会话ID格式 | 对应项目 |
|-----------|---------|
| `novel-海贼王之只手遮天` | 小说创作项目《海贼王之只手遮天》 |
| `imitate-神秘之旅改编` | 仿写项目《神秘之旅改编》 |
| `a3f1b2c4`（随机8位） | 普通对话 |

会话数据存储在 `{项目根目录}/.deepagents/sessions.db` 的 `checkpoints` 表中，`thread_id` 字段就是会话ID。

---

## 日志

```bash
# 查看日志列表
uv run deepagents logs list

# 查看某次对话的完整日志
uv run deepagents logs view <会话ID>

# 只看最近5条
uv run deepagents logs view <会话ID> --recent 5

# 查看日志存放路径
uv run deepagents logs path
```

---

## Agent管理

```bash
# 列出所有Agent
uv run deepagents list

# 重置某个Agent的记忆
uv run deepagents reset --agent mybot

# 查看帮助
uv run deepagents help
```

---

## 技能管理

```bash
# 列出所有技能
uv run deepagents skills list

# 创建新技能
uv run deepagents skills create my-skill

# 创建项目级技能（跟着项目走，不跟Agent走）
uv run deepagents skills create my-skill --project

# 查看某个技能的详情
uv run deepagents skills info my-skill
```

---

## 小说创作

```bash
# 创建小说项目
uv run deepagents novel init "海贼王之只手遮天" --world onepiece
uv run deepagents novel init "我的原创小说" --world original
uv run deepagents novel init "火影新传" -w naruto

# 查看所有小说项目
uv run deepagents novel list

# 查看某个项目的状态（进度、角色、伏笔等）
uv run deepagents novel status "海贼王之只手遮天"

# 开始创作（进入对话模式，Agent按阶段引导你）
uv run deepagents novel start "海贼王之只手遮天"

# 指定创作模式直接进入
uv run deepagents novel start "海贼王之只手遮天" --mode outline   # 写大纲
uv run deepagents novel start "海贼王之只手遮天" --mode write     # 写正文
uv run deepagents novel start "海贼王之只手遮天" --mode revise    # 修改润色

# 创建检查点（写到关键节点存个档）
uv run deepagents novel checkpoint "大纲完成"
uv run deepagents novel checkpoint list
uv run deepagents novel checkpoint restore <检查点ID>

# 旧项目迁移到SQLite格式
uv run deepagents novel migrate "海贼王之只手遮天"
uv run deepagents novel migrate "海贼王之只手遮天" --rollback       # 回滚迁移
```

---

## 小说仿写

```bash
# 创建仿写项目（指定源小说文件）
uv run deepagents novel imitate init "神秘之旅改编" --source ./神秘之旅.txt
uv run deepagents novel imitate init "神秘之旅改编" --source /home/lijie/test/deepagents-book/神秘之旅.txt   
                                              
uv run deepagents novel imitate init "新作" -s /path/to/novel.txt

# 开始仿写（进入对话模式，告诉Agent你想怎么改编）
uv run deepagents novel imitate start "神秘之旅改编"

# 查看仿写项目状态（源小说信息、已保存分析、已生成章节）
uv run deepagents novel imitate status "神秘之旅改编"
```

仿写会话中，Agent会自主完成：索引源小说 → 阅读章节 → 分析DNA → 推荐改编方案（S+/S/A-D多层次） → 逐章生成。你只需要用自然语言告诉它想做什么，比如"帮我仿写前三章"、"把主角换成女性"。
