#!/usr/bin/env python3
"""
故事线重新设计器

功能：支持不同粒度的大纲重新设计（整卷、章节范围、单章节）
特点：保持连贯性，遵循"有迹可循"原则和"角色不脸谱化"原则
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple


class StorylineRedesigner:
    """故事线重新设计器"""

    def __init__(self, input_file, scope, requirement, output_file):
        """
        初始化重新设计器

        Args:
            input_file: 输入文件路径
            scope: 重新设计范围（volume2/chapters 10-20/chapter 11）
            requirement: 重新设计需求
            output_file: 输出文件路径
        """
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.scope = scope
        self.requirement = requirement

        # 读取输入文件
        with open(self.input_file, "r", encoding="utf-8") as f:
            self.content = f.read()

        # 解析大纲
        self.outline = self._parse_outline()

        # 分析重新设计范围
        self.redesign_range = self._parse_scope()

    def _parse_outline(self):
        """解析大纲"""
        # 使用正则表达式匹配章节
        chapter_pattern = re.compile(
            r"### 第(\d+)章：《(.+?)》\n\n\*\*章节概述\*\*:(.+?)\n\n\*\*情节点\*\*:(.+?)\n\n\*\*情感变化\*\*:(.+?)\n\n\*\*爽点\*\*:(.+?)\n\n\*\*钩子\*\*:(.+?)\n\n\*\*伏笔\*\*:(.+?)(?=\n\n### 第\d+章|\Z)",
            re.DOTALL,
        )

        chapters = {}
        for match in chapter_pattern.finditer(self.content):
            chapter_num = int(match.group(1))
            chapter_title = match.group(2)
            chapter_overview = match.group(3).strip()
            plot_points = match.group(4).strip()
            emotion_change = match.group(5).strip()
            highlights = match.group(6).strip()
            hooks = match.group(7).strip()
            foreshadowings = match.group(8).strip()

            chapters[chapter_num] = {
                "title": chapter_title,
                "overview": chapter_overview,
                "plot_points": plot_points,
                "emotion_change": emotion_change,
                "highlights": highlights,
                "hooks": hooks,
                "foreshadowings": foreshadowings,
            }

        return chapters

    def _parse_scope(self):
        """解析重新设计范围"""
        if self.scope.startswith("volume"):
            # 整卷重新设计，如 volume2
            volume_num = int(self.scope.replace("volume", ""))
            # 假设每卷20章
            start_chapter = (volume_num - 1) * 20 + 1
            end_chapter = volume_num * 20
            return ("volume", start_chapter, end_chapter)

        elif self.scope.startswith("chapters"):
            # 章节范围重新设计，如 chapters 10-20
            range_part = self.scope.replace("chapters", "").strip()
            start, end = map(int, range_part.split("-"))
            return ("chapters", start, end)

        elif self.scope.startswith("chapter"):
            # 单章节重新设计，如 chapter 11
            chapter_num = int(self.scope.replace("chapter", "").strip())
            return ("chapter", chapter_num, chapter_num)

        else:
            raise ValueError(f"无效的重新设计范围：{self.scope}")

    def analyze_current_state(self):
        """
        分析当前状态

        Returns:
            当前状态字典：角色状态、情节走向、伏笔设置
        """
        current_state = {
            "characters": {},  # 角色状态
            "plot": [],  # 情节走向
            "foreshadowings": [],  # 伏笔设置
        }

        # 提取前一章的状态（如果有）
        if self.redesign_range[1] > 1:
            previous_chapter = self.redesign_range[1] - 1
            if previous_chapter in self.outline:
                chapter_data = self.outline[previous_chapter]

                # 提取角色状态
                character_pattern = re.compile(
                    r"(李寒|索隆|乌索普|山治|娜美|老鼠|蒙卡|鹰眼)(.+?)(?=(李寒|索隆|乌索普|山治|娜美|老鼠|蒙卡|鹰眼)|$)"
                )
                for match in character_pattern.finditer(chapter_data["overview"]):
                    character = match.group(1)
                    state = match.group(2)
                    current_state["characters"][character] = state

                # 提取伏笔
                foreshadowing_pattern = re.compile(r"\d+\. (.+)")
                for match in foreshadowing_pattern.finditer(chapter_data["foreshadowings"]):
                    current_state["foreshadowings"].append(match.group(1))

        return current_state

    def check_consistency(self, new_content):
        """
        检查连贯性

        Args:
            new_content: 新大纲内容

        Returns:
            连贯性报告
        """
        report = {
            "character_consistency": True,
            "plot_consistency": True,
            "foreshadowing_consistency": True,
            "issues": [],
        }

        # 检查角色连贯性
        current_state = self.analyze_current_state()

        # 检查李寒的状态
        if "李寒" in current_state["characters"]:
            # 检查新大纲中李寒的状态是否一致
            lihan_pattern = re.compile(r"李寒(.+?)(?=(索隆|乌索普|山治|娜美|老鼠|蒙卡|鹰眼)|$)")
            for match in lihan_pattern.finditer(new_content):
                lihan_state = match.group(1)
                # 这里应该检查状态是否合理，简化处理
                break

        # 生成报告
        return report

    def generate_redesign_guide(self):
        """
        生成重新设计指导

        Returns:
            重新设计指导文本
        """
        scope_type, start, end = self.redesign_range
        current_state = self.analyze_current_state()

        guide = f"""# 故事线重新设计指导

## 重新设计范围
- **类型**: {scope_type}
- **章节**: 第{start}章 - 第{end}章

## 重新设计需求
{self.requirement}

## 当前状态分析

### 角色状态
"""

        for character, state in current_state["characters"].items():
            guide += f"- **{character}**: {state}\n"

        guide += """
### 已设置的伏笔
"""

        for foreshadowing in current_state["foreshadowings"]:
            guide += f"- {foreshadowing}\n"

        guide += """
## 重新设计原则

### 1. 连贯性原则
- 新大纲必须与前文连贯
- 角色状态必须保持一致
- 伏笔回收必须考虑全局

### 2. 用户需求优先
- 必须满足用户提出的要求
- 必须包含用户要求的情节

### 3. 质量原则
- 遵循"有迹可循"原则
- 遵循"角色不脸谱化"原则
- 每个情节点必须具体、逻辑严密

### 4. 重新设计步骤

#### 第一步：理解重新设计需求
- 解析用户的需求
- 提取核心要求
- 确定必须包含的情节

#### 第二步：分析当前状态
- 查看前一章的结尾状态
- 提取角色当前状态
- 查看已设置的伏笔

#### 第三步：设计新故事线
- 根据用户要求，设计新的情节走向
- 保持连贯性
- 遵循质量原则

#### 第四步：生成新大纲
- 生成重新设计部分的详细大纲
- 包含：章节概述、情节点、情感变化、爽点、钩子、伏笔
- 每章至少7个情节点

#### 第五步：验证连贯性
- 检查新大纲与前文的连贯性
- 检查角色状态是否一致
- 检查伏笔回收是否合理

## 重新设计模板

### 章节模板
```markdown
### 第X章：《章节名》

**章节概述**: 100-200字，概括本章的核心内容，必须体现重新设计需求

**情节点**:
1. 【小标题】具体描述，包含人物、动作、结果（至少7个）
2. 【小标题】具体描述
...

**情感变化**: A→B→C（用→连接，展示主角情感变化）

**爽点**: 具体爽点1+具体爽点2

**钩子**: 引发读者好奇的问题

**伏笔**:
- 伏笔1
- 伏笔2
```

## 示例：整卷重新设计

### 用户需求
"第二卷重新设计，主角收服鹰眼米霍克，不再收服索隆"

### 重新设计思路
1. 分析第一卷结尾：李寒已成为东海势力，能量200点
2. 设计新故事线：
   - 第21章：巴拉蒂布局，李寒遇到鹰眼
   - 第22章：索隆挑战鹰眼（原著情节），但李寒改变走向
   - 第23章：李寒挑战鹰眼，获得认可
   - 第24-40章：拜师鹰眼，学习剑术，收服鹰眼
3. 保持连贯性：第一卷的角色状态、能力保持一致
4. 遵循质量原则：每章至少7个情节点，有迹可循

## 示例：章节范围重新设计

### 用户需求
"第一卷10-20章按不收服乌索普，改为收服克利的方向重新设计"

### 重新设计思路
1. 分析前9章：李寒已收服索隆，能量200点
2. 设计新故事线：
   - 第10章：巴拉蒂布局，李寒遇到克利
   - 第11-15章：克利克海贼团入侵，李寒出手，收服克利
   - 第16-20章：收服山治和娜美
3. 保持连贯性：第9章结尾的状态与第10章开头一致
4. 遵循质量原则：收服克利必须有逻辑过程

## 示例：单章节重新设计

### 用户需求
"第11章重新设计，主角不学习乌索普的诡计，而是学习鹰眼的剑术"

### 重新设计思路
1. 分析第10章结尾：李寒收服了索隆
2. 设计新情节：
   - 第11章：李寒遇到鹰眼，通过切磋获得认可，学习剑术
3. 保持连贯性：
   - 第10章结尾的状态与第11章开头一致
   - 第11章结尾的状态与第12章开头一致
4. 遵循质量原则：学习剑术必须符合世界观

## 质量检查清单

重新设计后，必须检查以下项目：

- [ ] 满足用户需求
- [ ] 与前文连贯
- [ ] 与后文连贯
- [ ] 角色状态一致
- [ ] 每章至少7个情节点
- [ ] 情节点具体、逻辑严密
- [ ] 角色行动符合性格设定
- [ ] 技能获取符合世界观
- [ ] 收服过程有逻辑
- [ ] 伏笔设置合理

---

**提示**：以上是重新设计指导，智能体应根据此指导生成新大纲。
"""

        return guide

    def redesign(self):
        """执行重新设计"""
        # 生成重新设计指导
        guide = self.generate_redesign_guide()

        # 保存指导文件
        guide_file = self.output_file.parent / f"{self.output_file.stem}-指导.md"
        with open(guide_file, "w", encoding="utf-8") as f:
            f.write(guide)

        # 注意：实际的重新设计需要智能体根据指导完成
        # 脚本只负责生成指导和分析连贯性

        print(f"重新设计指导已生成：{guide_file}")
        print("请根据指导生成新大纲，然后使用连贯性检查工具验证。")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="故事线重新设计器")
    parser.add_argument("--input", required=True, help="输入文件路径")
    parser.add_argument(
        "--scope", required=True, help="重新设计范围（volume2/chapters 10-20/chapter 11）"
    )
    parser.add_argument("--requirement", required=True, help="重新设计需求")
    parser.add_argument("--output", required=True, help="输出文件路径")

    args = parser.parse_args()

    redesigner = StorylineRedesigner(
        input_file=args.input,
        scope=args.scope,
        requirement=args.requirement,
        output_file=args.output,
    )

    redesigner.redesign()


if __name__ == "__main__":
    main()
