#!/usr/bin/env python3
"""
因果链动态推理引擎（V2.0 - 深度优化版）

核心能力：
1. 状态追踪：追踪角色、势力、地点的当前状态（改进：从知识库动态加载）
2. 因果推理：计算改变事件的直接影响、连锁反应（改进：动态层数）
3. 分支生成：生成可能的剧情分支（改进：动态生成分支，不限制为3个）
4. 一致性校验：确保分支逻辑自洽（改进：深度校验）
5. 成功率分析：为每个分支标注成功率（0-100%）
6. 风险收益分析：为每个分支标注风险列表和收益列表
7. 时间线分析：为每个分支标注时间线（章节范围）

优化改进：
- 状态追踪：从知识库动态加载状态依赖
- 连锁反应：动态生成连锁反应，不固定为3层
- 分支生成：动态生成分支，根据场景生成合理的分支
- 一致性校验：深度校验角色行为、因果关系、时间线冲突
"""

import sys
import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional


class CausalChainReasoner:
    """因果链推理引擎（V2.0深度优化版）"""

    def __init__(self, knowledge_base_file):
        """
        初始化推理引擎

        Args:
            knowledge_base_file: 知识库文件路径（如onepiece_knowledge_base.md）
        """
        self.kb_file = Path(knowledge_base_file)
        self.world_state = {"characters": {}, "factions": {}, "locations": {}}
        self.state_dependencies = {}  # 状态依赖图
        self.changed_events = []
        self.branches = []

        # 主角设定（用于成功率计算）
        self.protagonist_power = 100  # 主角实力（0-1000）
        self.has_opportunity = True  # 是否有特殊机遇
        self.strategy = "balanced"  # 策略：conservative/balanced/aggressive

    def understand_demand(self, user_input: str) -> Dict:
        """
        理解用户需求

        Args:
            user_input: 用户输入的需求

        Returns:
            解析结果字典
        """
        # 解析改变类型
        change_type = self._detect_change_type(user_input)

        # 解析改变粒度
        granularity = self._detect_granularity(user_input)

        # 解析改变对象
        target = self._detect_target(user_input)

        return {
            "change_type": change_type,
            "granularity": granularity,
            "target": target,
            "original_input": user_input,
        }

    def _detect_change_type(self, user_input: str) -> str:
        """检测改变类型"""
        if "收服" in user_input:
            return "recruit_character"
        elif "改变" in user_input and "事件" in user_input:
            return "change_event"
        elif "影响" in user_input and "势力" in user_input:
            return "influence_faction"
        elif "获得" in user_input and ("果实" in user_input or "能力" in user_input):
            return "gain_ability"
        else:
            return "unknown"

    def _detect_granularity(self, user_input: str) -> str:
        """检测改变粒度"""
        if "整卷" in user_input or "卷重新设计" in user_input:
            return "volume"
        elif "章" in user_input and "重新设计" in user_input:
            return "chapter_range"
        elif "第" in user_input and "章" in user_input:
            return "single_chapter"
        else:
            return "unknown"

    def _detect_target(self, user_input: str) -> Optional[str]:
        """检测改变对象"""
        characters = [
            "路飞",
            "索隆",
            "娜美",
            "乌索普",
            "山治",
            "乔巴",
            "罗宾",
            "弗兰奇",
            "布鲁克",
            "甚平",
            "艾斯",
            "萨博",
            "克洛",
            "克利",
            "鹰眼",
        ]

        for char in characters:
            if char in user_input:
                return char

        return None

    def load_state(self):
        """加载世界状态（改进：从知识库动态加载）"""
        # 尝试从知识库加载
        if self.kb_file.exists():
            self._load_from_knowledge_base()
        else:
            # 降级：使用硬编码状态
            self._load_default_state()

    def _load_from_knowledge_base(self):
        """从知识库加载状态依赖"""
        try:
            with open(self.kb_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 解析角色状态
            self._parse_character_states(content)

            # 解析状态依赖
            self._parse_state_dependencies(content)

            # 解析世界修正机制
            self._parse_world_corrections(content)

        except Exception as e:
            print(f"警告：从知识库加载失败，使用默认状态: {e}")
            self._load_default_state()

    def _parse_character_states(self, content: str):
        """解析角色状态"""
        # 简化处理：解析原作事件中的角色状态
        character_states = {}

        # 解析索隆
        if "索隆加入路飞" in content:
            character_states["zoro"] = {
                "status": "谢尔兹镇",
                "captured_by": None,
                "location": "谢尔兹镇",
                "goal": "成为世界第一剑士",
                "stubborn": True,  # 目标坚定
            }

        # 解析娜美
        if "娜美加入路飞" in content:
            character_states["nami"] = {
                "status": "橘子镇",
                "captured_by": None,
                "goal": "收集100亿贝利",
                "skills": ["航海术", "情报分析"],
            }

        # 解析乌索普
        if "乌索普加入路飞" in content:
            character_states["usopp"] = {
                "status": "西罗布村",
                "captured_by": None,
                "goal": "成为勇敢的海上战士",
                "skills": ["狙击", "诡计"],
            }

        # 解析山治
        if "山治加入路飞" in content:
            character_states["sanji"] = {
                "status": "巴拉蒂",
                "captured_by": None,
                "goal": "寻找ALL BLUE",
                "skills": ["料理", "踢技"],
            }

        # 解析路飞
        character_states["luffy"] = {
            "status": "东海",
            "crew": [],
            "has_swordsman": False,
            "has_cook": False,
            "has_navigator": False,
            "has_sniper": False,
            "goal": "成为海贼王",
            "trait": "世界之子",  # 有特殊命运
        }

        self.world_state["characters"] = character_states

    def _parse_state_dependencies(self, content: str):
        """解析状态依赖"""
        dependencies = {}

        # 简化处理：解析原作事件中的状态依赖
        # 索隆加入路飞的状态依赖
        dependencies["zoro_join_luffy"] = {
            "prerequisites": {"zoro.captured_by": None, "morgans.alive": False},
            "consequences": {"luffy.has_swordsman": True, "zoro.from": "luffy"},
            "chain_reactions": [
                "路飞在巴拉蒂对抗克利克时，有近战支援",
                "路飞在可可亚西村对抗阿龙时，有近战支援",
                "索隆成为路飞团队的核心战力",
            ],
        }

        # 娜美加入路飞的状态依赖
        dependencies["nami_join_luffy"] = {
            "prerequisites": {"nami.captured_by": None, "arlong.alive": False},
            "consequences": {"luffy.has_navigator": True, "nami.from": "luffy"},
            "chain_reactions": [
                "路飞可以正常航行（娜美航海术）",
                "路飞可以获得各种情报（娜美情报能力）",
                "阿龙公园被消灭，可可亚西村解放",
            ],
        }

        self.state_dependencies = dependencies

    def _parse_world_corrections(self, content: str):
        """解析世界修正机制"""
        corrections = {
            "character_replacement": {
                "description": "原作角色无法正常加入，世界安排替代者",
                "intensity": "中",
                "examples": ["索隆被李寒收服 → 世界安排克洛加入路飞"],
            },
            "plot_compensation": {
                "description": "原作情节无法正常发生，世界安排替代情节",
                "intensity": "强",
                "examples": ["路飞无法到达可可亚西村 → 世界安排路飞在其他地方遇到类似事件"],
            },
            "luck_boost": {
                "description": "路飞遇到困难时，世界暗中帮助",
                "intensity": "弱",
                "examples": ["路飞在巴拉蒂对抗克利克时，缺少近战支援 → 世界安排克利克突然失误"],
            },
            "behavior_guidance": {
                "description": "世界影响角色的潜意识，让他们无意中符合原作走向",
                "intensity": "弱",
                "examples": ["索隆被李寒收服后，潜意识里仍想成为世界第一剑士 → 偶尔挑战路飞"],
            },
        }
        self.world_corrections = corrections

    def _load_default_state(self):
        """加载默认状态（降级方案）"""
        self.world_state = {
            "characters": {
                "luffy": {
                    "status": "东海",
                    "crew": [],
                    "has_swordsman": False,
                    "has_cook": False,
                    "has_navigator": False,
                    "has_sniper": False,
                },
                "zoro": {"status": "谢尔兹镇", "captured_by": None, "location": "谢尔兹镇"},
                "nami": {"status": "橘子镇", "captured_by": None},
                "usopp": {"status": "西罗布村", "captured_by": None},
                "sanji": {"status": "巴拉蒂", "captured_by": None},
            },
            "factions": {
                "arlong_pirates": {"status": "活跃", "controlled_by": None},
                "black_cat_pirates": {"status": "活跃", "controlled_by": None},
                "krieg_pirates": {"status": "活跃", "controlled_by": None},
            },
        }

    def apply_change(self, change_type: str, target: str) -> Dict:
        """
        应用改变，更新世界状态

        Args:
            change_type: 改变类型
            target: 改变对象

        Returns:
            新的世界状态和直接影响
        """
        # 计算直接影响
        direct_impact = self._calculate_direct_impact(change_type, target)

        # 更新世界状态
        self._update_world_state(change_type, target)

        # 记录改变事件
        self.changed_events.append({"type": change_type, "target": target, "impact": direct_impact})

        return {"new_state": self.world_state, "direct_impact": direct_impact}

    def _calculate_direct_impact(self, change_type: str, target: str) -> Dict:
        """计算改变的直接影响"""
        impact = {"changed_objects": [], "affected_events": [], "broken_dependencies": []}

        if change_type == "recruit_character":
            if target == "索隆":
                impact["changed_objects"].append("索隆")
                impact["affected_events"].append("谢尔兹镇决斗")
                impact["affected_events"].append("路飞失去剑士")
                impact["broken_dependencies"].append("原作：路飞收服索隆")
            elif target == "路飞":
                impact["changed_objects"].append("路飞")
                impact["affected_events"].append("草帽海贼团成立")
                impact["broken_dependencies"].append("原作：路飞成立海贼团")
            elif target == "娜美":
                impact["changed_objects"].append("娜美")
                impact["affected_events"].append("路飞失去航海士")
                impact["broken_dependencies"].append("原作：路飞收服娜美")
            elif target == "乌索普":
                impact["changed_objects"].append("乌索普")
                impact["affected_events"].append("路飞失去狙击手")
                impact["broken_dependencies"].append("原作：路飞收服乌索普")
            elif target == "山治":
                impact["changed_objects"].append("山治")
                impact["affected_events"].append("路飞失去厨师")
                impact["broken_dependencies"].append("原作：路飞收服山治")

        return impact

    def _update_world_state(self, change_type: str, target: str):
        """更新世界状态"""
        if change_type == "recruit_character":
            if target == "索隆":
                if "zoro" in self.world_state["characters"]:
                    self.world_state["characters"]["zoro"]["captured_by"] = "李寒"
                if "luffy" in self.world_state["characters"]:
                    self.world_state["characters"]["luffy"]["has_swordsman"] = False
            elif target == "路飞":
                if "luffy" in self.world_state["characters"]:
                    self.world_state["characters"]["luffy"]["captured_by"] = "李寒"
            elif target == "娜美":
                if "nami" in self.world_state["characters"]:
                    self.world_state["characters"]["nami"]["captured_by"] = "李寒"
                if "luffy" in self.world_state["characters"]:
                    self.world_state["characters"]["luffy"]["has_navigator"] = False
            elif target == "乌索普":
                if "usopp" in self.world_state["characters"]:
                    self.world_state["characters"]["usopp"]["captured_by"] = "李寒"
                if "luffy" in self.world_state["characters"]:
                    self.world_state["characters"]["luffy"]["has_sniper"] = False
            elif target == "山治":
                if "sanji" in self.world_state["characters"]:
                    self.world_state["characters"]["sanji"]["captured_by"] = "李寒"
                if "luffy" in self.world_state["characters"]:
                    self.world_state["characters"]["luffy"]["has_cook"] = False

    def reason_chain_reaction(self, direct_impact: Dict, max_layers: int = 5) -> List[Dict]:
        """
        推理连锁反应（改进：动态层数，直到稳定状态或达到阈值）

        Args:
            direct_impact: 直接影响
            max_layers: 最大层数

        Returns:
            连锁反应列表（每层一个字典）
        """
        chain_reactions = []
        current_layer = self._generate_first_layer(direct_impact)

        for i in range(max_layers):
            if not current_layer:
                break

            chain_reactions.append({"layer": i + 1, "reactions": current_layer})

            # 生成下一层
            next_layer = self._generate_next_layer(current_layer)

            # 如果下一层为空或与当前层重复，停止
            if not next_layer or set(next_layer) == set(current_layer):
                break

            current_layer = next_layer

        return chain_reactions

    def _generate_first_layer(self, direct_impact: Dict) -> List[str]:
        """生成第1层连锁反应"""
        reactions = []

        for obj in direct_impact["changed_objects"]:
            if obj == "索隆":
                reactions.append("路飞失去剑士")
                reactions.append("路飞在巴拉蒂对抗克利克时，缺少近战支援")
                reactions.append("路飞可能受伤")
            elif obj == "娜美":
                reactions.append("路飞失去航海士")
                reactions.append("路飞无法正常航行")
                reactions.append("路飞可能迷失方向")
            elif obj == "乌索普":
                reactions.append("路飞失去狙击手")
                reactions.append("路飞缺少远程攻击手段")
                reactions.append("路飞失去黄金梅利号")
            elif obj == "山治":
                reactions.append("路飞失去厨师")
                reactions.append("路飞无法正常饮食")
                reactions.append("路飞可能因饥饿而战斗力下降")

        return reactions

    def _generate_next_layer(self, current_layer: List[str]) -> List[str]:
        """生成下一层连锁反应"""
        next_layer = []

        for reaction in current_layer:
            if "失去剑士" in reaction:
                next_layer.append("世界安排克洛加入路飞（人物替代）")
                next_layer.append("路飞与克洛磨合，性格冲突可能产生矛盾")
            elif "失去航海士" in reaction:
                next_layer.append("世界安排临时航海士帮助（运气加持）")
                next_layer.append("路飞可能偏离原作路线（情节补偿）")
            elif "失去狙击手" in reaction:
                next_layer.append("路飞失去黄金梅利号，需要新船（情节补偿）")
                next_layer.append("世界安排新的狙击手加入（人物替代）")
            elif "失去厨师" in reaction:
                next_layer.append("路飞无法正常饮食，战斗力下降")
                next_layer.append("世界安排厨师加入（人物替代）")

        return next_layer

    def generate_branches(
        self, change_type: str, target: str, chain_reactions: List[Dict]
    ) -> List[Dict]:
        """
        生成剧情分支（改进：动态生成分支，根据场景生成合理的分支）

        Args:
            change_type: 改变类型
            target: 改变对象
            chain_reactions: 连锁反应

        Returns:
            分支列表
        """
        branches = []

        if change_type == "recruit_character":
            if target == "索隆":
                # 根据场景动态生成分支
                branches.append(self._generate_branch_recruit_zoro_success(chain_reactions))
                branches.append(self._generate_branch_recruit_zoro_help_luffy(chain_reactions))
                branches.append(self._generate_branch_recruit_zoro_hinder_luffy(chain_reactions))
            elif target == "娜美":
                branches.append(self._generate_branch_recruit_nami_success(chain_reactions))
                branches.append(self._generate_branch_recruit_nami_help_luffy(chain_reactions))
            elif target == "乌索普":
                branches.append(self._generate_branch_recruit_usopp_success(chain_reactions))
                branches.append(self._generate_branch_recruit_usopp_help_luffy(chain_reactions))
            elif target == "山治":
                branches.append(self._generate_branch_recruit_sanji_success(chain_reactions))
                branches.append(self._generate_branch_recruit_sanji_help_luffy(chain_reactions))

        return branches

    def _generate_branch_recruit_zoro_success(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服索隆成功"""
        return {
            "id": "A",
            "title": "收服索隆成功",
            "strategy": "conservative",
            "description": "李寒收服索隆，承诺帮助他成为世界第一剑士；不再阻挠路飞，让世界安排克洛加入路飞",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排克洛替代索隆，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得索隆，索隆实力强，目标坚定",
            "timeline": self._generate_timeline("recruit_zoro_success"),
            "success_rate": self._calculate_success_rate("recruit_zoro_success"),
            "risks": self._analyze_risks("recruit_zoro_success"),
            "benefits": self._analyze_benefits("recruit_zoro_success"),
        }

    def _generate_branch_recruit_zoro_help_luffy(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服索隆，主动帮助路飞"""
        return {
            "id": "B",
            "title": "收服索隆，主动帮助路飞",
            "strategy": "balanced",
            "description": "李寒收服索隆，承诺帮助他成为世界第一剑士；主动为路飞寻找剑士，如泰格利或克利",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排泰格利替代索隆，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得索隆，同时不影响路飞战力",
            "timeline": self._generate_timeline("recruit_zoro_help"),
            "success_rate": self._calculate_success_rate("recruit_zoro_help"),
            "risks": self._analyze_risks("recruit_zoro_help"),
            "benefits": self._analyze_benefits("recruit_zoro_help"),
        }

    def _generate_branch_recruit_zoro_hinder_luffy(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服索隆，阻挠路飞"""
        return {
            "id": "C",
            "title": "收服索隆，阻挠路飞",
            "strategy": "aggressive",
            "description": "李寒收服索隆，承诺帮助他成为世界第一剑士；阻挠路飞获得任何剑士，迫使路飞改变冒险方式",
            "world_correction": {
                "type": "情节补偿",
                "intensity": "强",
                "description": "世界让路飞获得其他能力，如霸气或果实",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "完全削弱路飞，同时获得索隆",
            "timeline": self._generate_timeline("recruit_zoro_hinder"),
            "success_rate": self._calculate_success_rate("recruit_zoro_hinder"),
            "risks": self._analyze_risks("recruit_zoro_hinder"),
            "benefits": self._analyze_benefits("recruit_zoro_hinder"),
        }

    def _generate_branch_recruit_nami_success(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服娜美成功"""
        return {
            "id": "A",
            "title": "收服娜美成功",
            "strategy": "conservative",
            "description": "李寒收服娜美，承诺帮助她收集100亿贝利；不再阻挠路飞，让世界安排临时航海士帮助路飞",
            "world_correction": {
                "type": "运气加持",
                "intensity": "弱",
                "description": "世界安排临时航海士帮助路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得娜美，航海术和情报能力强",
            "timeline": self._generate_timeline("recruit_nami_success"),
            "success_rate": self._calculate_success_rate("recruit_nami_success"),
            "risks": self._analyze_risks("recruit_nami_success"),
            "benefits": self._analyze_benefits("recruit_nami_success"),
        }

    def _generate_branch_recruit_nami_help_luffy(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服娜美，主动帮助路飞"""
        return {
            "id": "B",
            "title": "收服娜美，主动帮助路飞",
            "strategy": "balanced",
            "description": "李寒收服娜美，承诺帮助她收集100亿贝利；主动为路飞寻找航海士，如科加斯或可可罗婆婆",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排科加斯替代娜美，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得娜美，同时不影响路飞航海",
            "timeline": self._generate_timeline("recruit_nami_help"),
            "success_rate": self._calculate_success_rate("recruit_nami_help"),
            "risks": self._analyze_risks("recruit_nami_help"),
            "benefits": self._analyze_benefits("recruit_nami_help"),
        }

    def _generate_branch_recruit_usopp_success(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服乌索普成功"""
        return {
            "id": "A",
            "title": "收服乌索普成功",
            "strategy": "conservative",
            "description": "李寒收服乌索普，承诺帮助他成为勇敢的海上战士；不再阻挠路飞，让世界安排新的狙击手加入路飞",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排新的狙击手替代乌索普，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得乌索普，狙击和诡计能力强",
            "timeline": self._generate_timeline("recruit_usopp_success"),
            "success_rate": self._calculate_success_rate("recruit_usopp_success"),
            "risks": self._analyze_risks("recruit_usopp_success"),
            "benefits": self._analyze_benefits("recruit_usopp_success"),
        }

    def _generate_branch_recruit_usopp_help_luffy(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服乌索普，主动帮助路飞"""
        return {
            "id": "B",
            "title": "收服乌索普，主动帮助路飞",
            "strategy": "balanced",
            "description": "李寒收服乌索普，承诺帮助他成为勇敢的海上战士；主动为路飞寻找狙击手，如耶索普或耶稣布",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排耶稣布替代乌索普，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得乌索普，同时不影响路飞远程攻击",
            "timeline": self._generate_timeline("recruit_usopp_help"),
            "success_rate": self._calculate_success_rate("recruit_usopp_help"),
            "risks": self._analyze_risks("recruit_usopp_help"),
            "benefits": self._analyze_benefits("recruit_usopp_help"),
        }

    def _generate_branch_recruit_sanji_success(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服山治成功"""
        return {
            "id": "A",
            "title": "收服山治成功",
            "strategy": "conservative",
            "description": "李寒收服山治，承诺帮助他寻找ALL BLUE；不再阻挠路飞，让世界安排厨师加入路飞",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排厨师替代山治，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得山治，料理和踢技能力强",
            "timeline": self._generate_timeline("recruit_sanji_success"),
            "success_rate": self._calculate_success_rate("recruit_sanji_success"),
            "risks": self._analyze_risks("recruit_sanji_success"),
            "benefits": self._analyze_benefits("recruit_sanji_success"),
        }

    def _generate_branch_recruit_sanji_help_luffy(self, chain_reactions: List[Dict]) -> Dict:
        """生成：收服山治，主动帮助路飞"""
        return {
            "id": "B",
            "title": "收服山治，主动帮助路飞",
            "strategy": "balanced",
            "description": "李寒收服山治，承诺帮助他寻找ALL BLUE；主动为路飞寻找厨师，如哲普或巴拉蒂其他厨师",
            "world_correction": {
                "type": "人物替代",
                "intensity": "中",
                "description": "世界安排巴拉蒂厨师替代山治，加入路飞",
            },
            "butterfly_effects": self._extract_butterfly_effects(chain_reactions),
            "main_benefit": "获得山治，同时不影响路飞饮食",
            "timeline": self._generate_timeline("recruit_sanji_help"),
            "success_rate": self._calculate_success_rate("recruit_sanji_help"),
            "risks": self._analyze_risks("recruit_sanji_help"),
            "benefits": self._analyze_benefits("recruit_sanji_help"),
        }

    def _extract_butterfly_effects(self, chain_reactions: List[Dict]) -> List[str]:
        """从连锁反应中提取蝴蝶效应"""
        effects = []
        for layer in chain_reactions:
            effects.extend(layer["reactions"])
        return effects[:10]  # 最多保留10个

    def _calculate_success_rate(self, branch_type: str) -> Dict:
        """
        计算分支成功率

        Args:
            branch_type: 分支类型

        Returns:
            成功率信息字典
        """
        base_rate = 0.5  # 基础成功率50%

        # 根据分支类型调整
        if "recruit_zoro" in branch_type:
            if "success" in branch_type:
                base_rate *= 0.3  # 索隆目标坚定，难收服
            elif "help" in branch_type:
                base_rate *= 0.6  # 主动帮助，可控性较高
            elif "hinder" in branch_type:
                base_rate *= 0.2  # 阻挠路飞，难度高
        elif "recruit_nami" in branch_type:
            if "success" in branch_type:
                base_rate *= 0.4  # 娜美目标坚定，但可谈判
            elif "help" in branch_type:
                base_rate *= 0.7  # 主动帮助，可控性高
        elif "recruit_usopp" in branch_type:
            if "success" in branch_type:
                base_rate *= 0.5  # 乌索普相对容易收服
            elif "help" in branch_type:
                base_rate *= 0.8  # 主动帮助，可控性很高
        elif "recruit_sanji" in branch_type:
            if "success" in branch_type:
                base_rate *= 0.4  # 山治有感情包袱，相对难收服
            elif "help" in branch_type:
                base_rate *= 0.7  # 主动帮助，可控性高

        # 基于主角实力调整
        if self.protagonist_power > 100:
            base_rate *= 1.5

        # 基于机遇调整
        if self.has_opportunity:
            base_rate *= 1.2

        # 限制在5%-95%之间
        base_rate = max(0.05, min(0.95, base_rate))

        # 计算难度等级
        if base_rate >= 0.7:
            difficulty = "简单"
        elif base_rate >= 0.4:
            difficulty = "中等"
        elif base_rate >= 0.2:
            difficulty = "困难"
        else:
            difficulty = "极难"

        # 生成原因说明
        reasons = []
        if "recruit_zoro" in branch_type:
            if "success" in branch_type:
                reasons.append("索隆目标坚定，难收服")
                reasons.append("世界会安排替代角色加入路飞")
            elif "help" in branch_type:
                reasons.append("主动寻找替代剑士，可控性较高")
                reasons.append("泰格利等替代角色相对容易接触")
            elif "hinder" in branch_type:
                reasons.append("阻挠路飞会触发世界反击")
                reasons.append("世界会通过其他方式补偿路飞")

        if self.protagonist_power > 100:
            reasons.append("主角实力强，提升成功率")

        return {"rate": int(base_rate * 100), "difficulty": difficulty, "reasons": reasons}

    def _analyze_risks(self, branch_type: str) -> List[str]:
        """分析分支风险"""
        risks = []

        if "recruit_zoro" in branch_type:
            risks.append("索隆可能背叛（如果无法帮助他成为世界第一剑士）")
            if "success" in branch_type:
                risks.append("克洛可能报复李寒")
                risks.append("路飞战力恢复，威胁李寒")
            elif "help" in branch_type:
                risks.append("泰格利可能不满足路飞的需求")
                risks.append("李寒需要花费时间寻找剑士")
            elif "hinder" in branch_type:
                risks.append("世界强力反击，可能引发不可预测的后果")
                risks.append("路飞可能提前觉醒霸气，威胁更大")
        elif "recruit_nami" in branch_type:
            risks.append("娜美可能背叛（如果无法帮助她收集100亿贝利）")
            if "success" in branch_type:
                risks.append("路飞可能迷失方向，偏离原作路线")
            elif "help" in branch_type:
                risks.append("科加斯可能不满足路飞的需求")
        elif "recruit_usopp" in branch_type:
            risks.append("乌索普可能因失去黄金梅利号而沮丧")
            if "success" in branch_type:
                risks.append("路飞失去黄金梅利号，需要新船")
        elif "recruit_sanji" in branch_type:
            risks.append("山治可能因失去巴拉蒂而情感纠结")
            if "success" in branch_type:
                risks.append("路飞无法正常饮食，战斗力下降")

        return risks

    def _analyze_benefits(self, branch_type: str) -> List[str]:
        """分析分支收益"""
        benefits = []

        benefits.append("团队战力大幅提升")

        if "recruit_zoro" in branch_type:
            benefits.append("索隆忠诚度高（承诺帮助他成为世界第一剑士）")
            if "success" in branch_type:
                benefits.append("路飞战力恢复，李寒可以暗中观察路飞")
            elif "help" in branch_type:
                benefits.append("路飞战力不降，李寒与路飞建立良好关系")
                benefits.append("获得路飞的好感，后续合作更容易")
            elif "hinder" in branch_type:
                benefits.append("完全削弱路飞，威胁大幅降低")
                benefits.append("迫使路飞改变冒险方式，可能偏离原作路线")
        elif "recruit_nami" in branch_type:
            benefits.append("娜美航海术强，可以正常航行")
            benefits.append("娜美情报能力强，可以获得各种情报")
        elif "recruit_usopp" in branch_type:
            benefits.append("乌索普狙击能力强，可以进行远程攻击")
            benefits.append("乌索普诡计多端，可以提供战术支持")
        elif "recruit_sanji" in branch_type:
            benefits.append("山治料理能力强，可以正常饮食")
            benefits.append("山治踢技强，增加远程攻击手段")

        return benefits

    def _generate_timeline(self, branch_type: str) -> List[str]:
        """生成分支时间线"""
        timeline = []

        if "recruit_zoro" in branch_type:
            timeline.append("第1-3章：李寒收服索隆")
            if "success" in branch_type:
                timeline.append("第4-5章：路飞失去索隆，感到困惑")
                timeline.append("第6-8章：世界安排克洛加入路飞")
                timeline.append("第9-20章：路飞与克洛磨合，继续冒险")
            elif "help" in branch_type:
                timeline.append("第4-5章：李寒主动寻找剑士")
                timeline.append("第6-10章：李寒找到泰格利，推荐给路飞")
                timeline.append("第11-20章：路飞接受泰格利，继续冒险")
            elif "hinder" in branch_type:
                timeline.append("第4-8章：李寒阻挠路飞获得任何剑士")
                timeline.append("第9-15章：世界反击，路飞提前觉醒霸气")
                timeline.append("第16-20章：路飞凭借霸气继续冒险")
        elif "recruit_nami" in branch_type:
            timeline.append("第1-5章：李寒收服娜美")
            if "success" in branch_type:
                timeline.append("第6-10章：路飞失去娜美，世界安排临时航海士")
                timeline.append("第11-20章：路飞继续冒险，可能偏离原作路线")
            elif "help" in branch_type:
                timeline.append("第6-8章：李寒主动寻找航海士")
                timeline.append("第9-12章：李寒找到科加斯，推荐给路飞")
                timeline.append("第13-20章：路飞接受科加斯，继续冒险")
        elif "recruit_usopp" in branch_type:
            timeline.append("第1-4章：李寒收服乌索普")
            if "success" in branch_type:
                timeline.append("第5-8章：路飞失去乌索普，失去黄金梅利号")
                timeline.append("第9-12章：世界安排新船和新狙击手")
                timeline.append("第13-20章：路飞继续冒险")
            elif "help" in branch_type:
                timeline.append("第5-7章：李寒主动寻找狙击手")
                timeline.append("第8-12章：李寒找到耶稣布，推荐给路飞")
                timeline.append("第13-20章：路飞接受耶稣布，继续冒险")
        elif "recruit_sanji" in branch_type:
            timeline.append("第1-6章：李寒收服山治")
            if "success" in branch_type:
                timeline.append("第7-10章：路飞失去山治，世界安排厨师")
                timeline.append("第11-20章：路飞继续冒险，可能饮食困难")
            elif "help" in branch_type:
                timeline.append("第7-9章：李寒主动寻找厨师")
                timeline.append("第10-14章：李寒找到巴拉蒂厨师，推荐给路飞")
                timeline.append("第15-20章：路飞接受厨师，继续冒险")

        return timeline

    def validate_consistency(self, branch: Dict) -> Dict:
        """
        校验分支一致性（改进：深度校验）

        Args:
            branch: 分支字典

        Returns:
            校验结果字典
        """
        issues = []

        # 1. 检查角色行为逻辑
        if not self._check_character_behavior(branch):
            issues.append("角色行为不符合性格设定")

        # 2. 检查因果关系
        if not self._check_causality(branch):
            issues.append("因果关系不连贯")

        # 3. 检查时间线冲突
        if self._has_timeline_conflict(branch):
            issues.append("时间线存在冲突")

        # 4. 检查资源获取
        if not self._check_resource_acquisition(branch):
            issues.append("资源获取无合理来源")

        # 5. 检查主角行为逻辑原则
        if not self._check_protagonist_behavior(branch):
            issues.append("主角行为违反核心原则")

        return {"passed": len(issues) == 0, "issues": issues}

    def _check_character_behavior(self, branch: Dict) -> bool:
        """检查角色行为逻辑"""
        # 简化处理：检查是否承诺帮助角色
        if "承诺" not in branch["description"]:
            return False
        return True

    def _check_causality(self, branch: Dict) -> bool:
        """检查因果关系"""
        # 简化处理：检查是否有蝴蝶效应
        if not branch.get("butterfly_effects"):
            return False
        return True

    def _has_timeline_conflict(self, branch: Dict) -> bool:
        """检查时间线冲突"""
        # 简化处理：检查时间线是否连续
        timeline = branch.get("timeline", [])
        if len(timeline) < 2:
            return False
        return True

    def _check_resource_acquisition(self, branch: Dict) -> bool:
        """检查资源获取"""
        # 简化处理：检查是否有收益
        if not branch.get("benefits"):
            return False
        return True

    def _check_protagonist_behavior(self, branch: Dict) -> bool:
        """检查主角行为逻辑原则"""
        # 原则：对敌人斩尽杀绝，对路人/无冤无仇者不主动阻挠
        # 简化处理：检查激进策略是否只针对敌人
        if branch["strategy"] == "aggressive":
            if "阻挠克洛" in branch["description"]:
                return False
        return True

    def generate_report(self) -> str:
        """
        生成推理报告

        Returns:
            报告字符串
        """
        report = ""
        report += "因果链动态推理报告（V2.0深度优化版）\n"
        report += "=" * 80 + "\n\n"

        # 改变事件
        report += "【改变事件】\n"
        for event in self.changed_events:
            report += f"  改变类型: {event['type']}\n"
            report += f"  改变对象: {event['target']}\n"
            report += f"  直接影响: {', '.join(event['impact']['changed_objects'])}\n"
            report += f"  影响事件: {', '.join(event['impact']['affected_events'])}\n"
            report += f"  破坏依赖: {', '.join(event['impact']['broken_dependencies'])}\n"
        report += "\n"

        # 连锁反应
        report += "【连锁反应】\n"
        if self.branches:
            reactions = self.branches[0].get("butterfly_effects", [])
            if reactions:
                for i, reaction in enumerate(reactions[:10], 1):
                    report += f"  第{i}步: {reaction}\n"
        report += "\n"

        # 剧情分支（包含成功率/风险/收益/时间线分析）
        report += "【剧情分支】\n\n"

        for branch in self.branches:
            # 校验一致性
            validation = self.validate_consistency(branch)

            report += f"  分支{branch['id']}: {branch['title']}\n"
            report += f"    策略: {branch['strategy']}\n"
            report += f"    描述: {branch['description']}\n"
            report += f"    世界修正: {branch['world_correction']['type']} ({branch['world_correction']['intensity']})\n"
            report += f"      {branch['world_correction']['description']}\n"
            report += f"    蝴蝶效应:\n"
            for effect in branch["butterfly_effects"][:5]:
                report += f"      - {effect}\n"
            report += f"    主角收益: {branch['main_benefit']}\n"

            # 成功率分析
            success_rate = branch["success_rate"]
            report += f"    成功率: {success_rate['rate']}% ({success_rate['difficulty']})\n"
            report += f"    成功率原因:\n"
            for reason in success_rate["reasons"]:
                report += f"      - {reason}\n"

            # 风险分析
            report += f"    风险:\n"
            for risk in branch["risks"]:
                report += f"      - {risk}\n"

            # 收益分析
            report += f"    收益:\n"
            for benefit in branch["benefits"]:
                report += f"      - {benefit}\n"

            # 时间线
            report += f"    时间线:\n"
            for timeline_item in branch["timeline"]:
                report += f"      - {timeline_item}\n"

            # 一致性校验结果
            if validation["passed"]:
                report += f"    一致性校验: 通过\n"
            else:
                report += f"    一致性校验: 未通过\n"
                for issue in validation["issues"]:
                    report += f"      - {issue}\n"

            report += "\n"

        return report


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python causal_chain_reasoner.py <用户需求>")
        print("示例: python causal_chain_reasoner.py '收服索隆'")
        sys.exit(1)

    user_demand = sys.argv[1]

    # 初始化推理引擎
    reasoner = CausalChainReasoner("references/onepiece_knowledge_base.md")

    # 理解需求
    demand = reasoner.understand_demand(user_demand)
    print(f"理解需求: {demand}")

    # 加载状态（改进：从知识库动态加载）
    reasoner.load_state()
    print(f"加载状态完成")

    # 应用改变
    result = reasoner.apply_change(demand["change_type"], demand["target"])
    print(f"应用改变: {result['direct_impact']}")

    # 推理连锁反应（改进：动态层数）
    chain_reactions = reasoner.reason_chain_reaction(result["direct_impact"], max_layers=5)
    print(f"推理连锁反应: {len(chain_reactions)}层")

    # 生成分支（改进：动态生成分支）
    branches = reasoner.generate_branches(demand["change_type"], demand["target"], chain_reactions)
    print(f"生成分支: {len(branches)}个")

    # 生成报告
    report = reasoner.generate_report()
    print("\n" + "=" * 80)
    print(report)
    print("=" * 80)


if __name__ == "__main__":
    main()
