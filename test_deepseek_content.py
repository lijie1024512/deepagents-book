"""测试 DeepSeek API Content Exists Risk 触发点.

逐步添加内容，定位是哪部分触发风控。
用法: DEEPSEEK_API_KEY=xxx python test_deepseek_content.py
"""

import os
import sys

from openai import OpenAI

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

if not API_KEY:
    print("请设置 DEEPSEEK_API_KEY 环境变量")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def test_call(label: str, system: str, user: str) -> bool:
    """发送一次请求，返回是否成功。"""
    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"  system 长度: {len(system)} 字符")
    print(f"  user 长度: {len(user)} 字符")
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=100,
        )
        text = resp.choices[0].message.content[:100]
        print(f"  ✅ 成功: {text}...")
        return True
    except Exception as e:
        err = str(e)
        if "Content Exists Risk" in err:
            print(f"  ❌ Content Exists Risk!")
        else:
            print(f"  ❌ 其他错误: {err[:200]}")
        return False


# ============================================================
# 逐步测试
# ============================================================

# --- 第1组: 最简单的基线 ---
test_call(
    "1. 纯净基线",
    "你是一个写作助手。",
    "帮我写一个故事开头",
)

# --- 第2组: 加上"仿写"关键词 ---
test_call(
    "2. 仿写关键词",
    "你是一个写作助手。",
    "帮我仿写一个小说的第一章",
)

# --- 第3组: 加上小说标题 ---
test_call(
    "3. 仿写 + 小说标题",
    "你是一个写作助手。",
    "帮我仿写神秘之旅的第一章",
)

# --- 第4组: system里提到仿写 ---
test_call(
    "4. system含仿写指令",
    "你是一位专业的仿写编辑。帮助用户基于源小说进行仿写创作。",
    "帮我仿写第一章",
)

# --- 第5组: system含仿写+小说标题 ---
test_call(
    "5. system含仿写+标题",
    "你是一位专业的仿写编辑。你正在帮助用户基于源小说进行仿写创作，生成改编小说《神秘之旅改编》。",
    "帮我仿写第一章",
)

# --- 第6组: 用"创意改编"替代"仿写" ---
test_call(
    "6. 创意改编替代仿写",
    "你是一位专业的改编编辑。你正在帮助用户基于源小说进行创意改编，生成改编小说《神秘之旅改编》。",
    "帮我改编第一章",
)

# --- 第7组: 完整system prompt (无SKILL) ---
SYSTEM_BASE = """### 小说仿写会话

你正在帮助用户基于源小说进行仿写创作，生成改编小说《神秘之旅改编》。

**项目信息**:
- 标题: 神秘之旅改编
- 模式: 仿写

**你的角色**:
你是一位专业的仿写编辑。根据用户的请求自主决定工作流程。

**核心原则**:
- 仿写 ≠ 抄袭：继承结构DNA（文风节奏、叙事模式、爽点分布），在人物、金手指、具体情节上做创造性改造
- 原文是最好的老师：生成每章时参考源小说对应章节的原文来模仿文风
- 金手指要换"具体实现"，保留"结构DNA"
"""

test_call(
    "7. 完整基础system(含仿写+标题+原则)",
    SYSTEM_BASE,
    "帮我仿写第一章",
)

# --- 第8组: 只有标题没有仿写 ---
test_call(
    "8. 只有标题没有仿写",
    "你是一个写作助手。你正在帮助用户创作小说《神秘之旅改编》。",
    "帮我写第一章",
)

# --- 第9组: 有仿写没有标题 ---
test_call(
    "9. 有仿写没有标题",
    "你是一位专业的仿写编辑。帮助用户基于一部源小说进行仿写创作。",
    "帮我仿写第一章",
)

# --- 第10组: 章节目录（5章） ---
CHAPTER_INDEX = """源小说索引完成！
- 编码: gbk
- 总字符数: 5,147,757
- 检测到章节数: 1372

章节目录（前5章）:
  1. 第一卷 初始 1 (5,877字)
  2. 第一节课是数学 (94字)
  3. 第三节课是礼仪 (8,771字)
  4. 5 郊游 (3,432字)
  5. 6 建立科目项 (4,013字)
  ... 共 1372 章"""

test_call(
    "10. system含仿写 + 章节目录在user消息",
    "你是一位专业的仿写编辑。帮助用户仿写小说。",
    f"以下是源小说目录：\n{CHAPTER_INDEX}\n\n帮我仿写第一章",
)

# --- 第11组: 模拟多轮对话(tool result含目录) ---
print(f"\n{'='*60}")
print("测试: 11. 多轮对话(含tool result)")
print(f"  模拟 agent 调用 index_source 后的场景")
try:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是一位专业的仿写编辑。帮助用户基于源小说进行仿写创作，生成改编小说《神秘之旅改编》。",
            },
            {"role": "user", "content": "帮我仿写第一章"},
            {
                "role": "assistant",
                "content": "好的，我先建立源小说索引。",
            },
            {
                "role": "user",
                "content": f"[工具返回]\n{CHAPTER_INDEX}",
            },
        ],
        max_tokens=100,
    )
    text = resp.choices[0].message.content[:100]
    print(f"  ✅ 成功: {text}...")
except Exception as e:
    err = str(e)
    if "Content Exists Risk" in err:
        print(f"  ❌ Content Exists Risk!")
    else:
        print(f"  ❌ 其他错误: {err[:200]}")


print("\n" + "=" * 60)
print("测试完成！根据上面 ✅/❌ 的结果可以定位触发点。")
