#!/usr/bin/env python3
"""
小说大纲生成器

功能：根据基础设定生成高质量的小说大纲
特点：遵循"有迹可循"原则，拒绝脸谱化，角色逻辑严密
"""

import sys
import re
from pathlib import Path
from typing import List, Dict


class OutlineGenerator:
    """大纲生成器"""

    def __init__(self, world_file, character_file, storyline_file, chapters=20):
        """
        初始化生成器

        Args:
            world_file: 世界观文件路径
            character_file: 主角角色文件路径
            storyline_file: 故事线文件路径
            chapters: 目标章节数
        """
        self.world_file = Path(world_file)
        self.character_file = Path(character_file)
        self.storyline_file = Path(storyline_file)
        self.chapters = chapters

        # 加载设定
        self.world_config = self._load_yaml(self.world_file)
        self.character_config = self._load_yaml(self.character_file)
        self.storyline_config = self._load_yaml(self.storyline_file)

    def _load_yaml(self, file_path):
        """加载YAML文件"""
        import yaml

        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def generate(self, output_file):
        """
        生成大纲

        Args:
            output_file: 输出文件路径
        """
        # 生成基础信息部分
        content = self._generate_basic_info()

        # 生成系统设定部分（如果有）
        content += self._generate_system_info()

        # 生成主角角色卡部分
        content += self._generate_character_card()

        # 生成故事线结构部分
        content += self._generate_storyline()

        # 写入文件
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"大纲生成完成，共{self.chapters}章，输出文件：{output_file}")

    def _generate_basic_info(self):
        """生成基础信息部分"""
        world = self.world_config
        character = self.character_config

        content = f"""# {world["novel_name"]}

## 小说基础信息

【小说名称】: {world["novel_name"]}
【世界观】: {world["world_setting"]}
【主角金手指】: {character["cheat"]}
【主角性格类型】: {character["personality"]}
【故事线模式】: {world["storyline_mode"]}
【原创程度】: {world["originality"]}
【风格定位】: {world["style"]}
【预计篇幅】: {world["length"]}
【更新频率】: {world["update_frequency"]}

---

"""
        return content

    def _generate_system_info(self):
        """生成系统设定部分"""
        cheat = self.character_config.get("cheat", "")

        if "系统" not in cheat:
            return ""

        content = f"""## {cheat}设定

### 系统功能
```
{cheat} = 加点系统
唯一作用：给已经获得的技能加点，让技能变强
```

### 加点规则
- 技能等级: 入门 → 熟练 → 精通 → 大师 → 宗师 → 极境
- 能量来源: 军衔晋升

### 能量机制
军衔层级        | 能量上限 | 能量恢复速度
================================================================
三等兵        | 10点     | 1点/天
二等兵        | 30点     | 3点/天
一等兵        | 80点     | 8天/点
伍长          | 200点    | 20点/天
...（根据实际情况补充）
================================================================

---

"""
        return content

    def _generate_character_card(self):
        """生成主角角色卡部分"""
        character = self.character_config

        content = f"""## 主角角色卡

【基本信息】
姓名: {character["name"]}
年龄: {character["age"]}
性别: {character["gender"]}
种族: {character["race"]}
身份: {character["identity"]}
外貌特征: {character["appearance"]}

【力量属性】
霸气等级: {character["haki_level"]}
能力类型: {character["ability_type"]}
特长领域: {character["specialties"]}
弱点: {character["weakness"]}

【特殊能力】

**{character["cheat"]}**:
唯一功能: {character["cheat_function"]}
能量来源: {character["energy_source"]}

【性格深度】

**核心性格**: {character["core_personality"]}

**表面性格vs真实性格**:
  - 表面（开局）: {character["surface_personality_start"]}
  - 真实（开局）: {character["real_personality_start"]}
  - 真实（中期）: {character["real_personality_mid"]}
  - 真实（后期）: {character["real_personality_end"]}

【背景故事】
出身: {character["background"]}
成长经历: {character["growth"]}
关键转折: {character["turning_point"]}
当前状态: {character["current_state"]}

---

"""
        return content

    def _generate_storyline(self):
        """生成故事线结构部分"""
        storyline = self.storyline_config

        content = f"""## 故事线结构

### 第一卷：{storyline["volume1_name"]}（1-{self.chapters}章）

#### 卷概述
**核心主题**: {storyline["volume1_theme"]}
**核心冲突**: {storyline["volume1_conflict"]}
**主角目标**: {storyline["volume1_goals"]}
**本卷收获**: {storyline["volume1_harvest"]}
**关键事件**: {storyline["volume1_events"]}

---

"""

        # 生成详细章节
        for i in range(1, self.chapters + 1):
            content += self._generate_chapter(i)

        return content

    def _generate_chapter(self, chapter_num):
        """
        生成单个章节

        Args:
            chapter_num: 章节号

        Returns:
            章节文本
        """
        # 这里只是生成框架，实际内容应该根据故事线设定生成
        # 具体的情节点、情感变化、爽点、钩子、伏笔需要智能体根据上下文生成

        content = f"""### 第{chapter_num}章：《章节标题》

**章节概述**: 本章的核心内容（待根据故事线生成）

**情节点**:
1. 【小标题】具体描述（待生成）
2. 【小标题】具体描述（待生成）
3. 【小标题】具体描述（待生成）
...

**情感变化**: A→B→C（待生成）

**爽点**: 具体爽点（待生成）

**钩子**: 引发读者好奇的问题（待生成）

**伏笔**:
- 伏笔1（待生成）
- 伏笔2（待生成）

---

"""

        return content


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="小说大纲生成器")
    parser.add_argument("--world", required=True, help="世界观文件路径")
    parser.add_argument("--character", required=True, help="主角角色文件路径")
    parser.add_argument("--storyline", required=True, help="故事线文件路径")
    parser.add_argument("--chapters", type=int, default=20, help="目标章节数")
    parser.add_argument("--output", required=True, help="输出文件路径")

    args = parser.parse_args()

    generator = OutlineGenerator(
        world_file=args.world,
        character_file=args.character,
        storyline_file=args.storyline,
        chapters=args.chapters,
    )

    generator.generate(args.output)


if __name__ == "__main__":
    main()
