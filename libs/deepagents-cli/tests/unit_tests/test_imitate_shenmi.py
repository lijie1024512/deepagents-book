"""仿写测试：以《神秘之旅》前两章为例，测试完整仿写工作流。

包含：
- 源小说索引与章节读取（使用真实源文件，需较长超时）
- DNA分析与仿写方案保存
- 角色映射与金手指改编
- 前两章仿写生成与保存
- 生成上下文完整性验证
"""

import json
import re
from pathlib import Path

import pytest

from deepagents_cli.novel.database import NovelDatabase
from deepagents_cli.novel.imitate_tools import (
    _build_skill_library_prompt,
    _get_db,
    get_analysis,
    get_generation_context,
    get_project_status,
    index_source,
    read_source_chapter,
    read_source_range,
    record_writing_skill,
    save_analysis,
    save_chapter,
    search_source,
    setup_imitate_project,
)

# ---------------------------------------------------------------------------
# 源小说路径（需要实际文件存在才能运行）
# ---------------------------------------------------------------------------
SOURCE_NOVEL = (
    Path(__file__).resolve().parents[4] / "novels" / "神秘之旅改编" / "source" / "神秘之旅.txt"
)

# 索引大文件需要较长时间（~30s for 9.8MB GBK file）
INDEX_TIMEOUT = 120


@pytest.fixture
def shenmi_project(tmp_path):
    """基于真实《神秘之旅》源文件创建仿写项目。"""
    if not SOURCE_NOVEL.exists():
        pytest.skip(f"源小说文件不存在: {SOURCE_NOVEL}")

    project_path = tmp_path / "shenmi_imitate"
    project_path.mkdir()
    (project_path / ".novel").mkdir()

    NovelDatabase(project_path)
    setup_imitate_project(project_path, SOURCE_NOVEL, "神秘之旅仿写")
    return project_path


# ===========================================================================
# 第一部分：源小说索引与章节读取
# ===========================================================================
@pytest.mark.timeout(INDEX_TIMEOUT)
class TestSourceIndexing:
    """测试源小说索引功能。"""

    def test_index_detects_encoding_gbk(self, shenmi_project):
        """源小说应被检测为GBK编码。"""
        result = index_source.invoke({})
        assert "gbk" in result.lower()

    def test_index_detects_chapters(self, shenmi_project):
        """应检测到1000+章节。"""
        result = index_source.invoke({})
        assert "索引完成" in result
        # 验证数据库中章节数
        db = _get_db()
        with db._connection() as conn:
            row = conn.execute("SELECT total_chapters FROM imitate_source WHERE id=1").fetchone()
        assert row[0] > 1000

    def test_index_shows_first_chapter_title(self, shenmi_project):
        """目录应显示第一卷标题。"""
        result = index_source.invoke({})
        assert "初始" in result

    def test_total_chars_over_5_million(self, shenmi_project):
        """总字符数应超过500万。"""
        index_source.invoke({})
        db = _get_db()
        with db._connection() as conn:
            row = conn.execute("SELECT total_chars FROM imitate_source WHERE id=1").fetchone()
        assert row[0] > 5_000_000


@pytest.mark.timeout(INDEX_TIMEOUT)
class TestReadChapters:
    """测试前两章读取。"""

    def test_chapter1_contains_protagonist(self, shenmi_project):
        """第1章应包含主角罗靖/加隆。"""
        index_source.invoke({})
        ch1 = read_source_chapter.invoke({"chapter": 1})
        assert "罗靖" in ch1
        assert "加隆" in ch1

    def test_chapter1_has_transmigration(self, shenmi_project):
        """第1章应包含穿越情节。"""
        index_source.invoke({})
        ch1 = read_source_chapter.invoke({"chapter": 1})
        assert "穿越" in ch1

    def test_chapter1_char_count(self, shenmi_project):
        """第1章约3900字。"""
        index_source.invoke({})
        ch1 = read_source_chapter.invoke({"chapter": 1})
        assert 3000 < len(ch1) < 5000

    def test_chapter2_contains_power_system(self, shenmi_project):
        """第2章应出现属性面板（金手指）。"""
        index_source.invoke({})
        ch2 = read_source_chapter.invoke({"chapter": 2})
        assert "力量" in ch2
        assert "敏捷" in ch2
        assert "潜能" in ch2

    def test_chapter2_school_scene(self, shenmi_project):
        """第2章应包含学院场景。"""
        index_source.invoke({})
        ch2 = read_source_chapter.invoke({"chapter": 2})
        assert "圣莺" in ch2 or "学院" in ch2

    def test_read_range_covers_both_chapters(self, shenmi_project):
        """范围读取应覆盖两章内容。"""
        index_source.invoke({})
        text = read_source_range.invoke({"start_chapter": 1, "end_chapter": 2})
        assert "罗靖" in text  # 第1章
        assert "潜能" in text  # 第2章

    def test_search_protagonist(self, shenmi_project):
        """搜索加隆应返回多处匹配。"""
        index_source.invoke({})
        result = search_source.invoke({"keyword": "加隆", "max_results": 5})
        assert "匹配" in result
        assert "加隆" in result


# ===========================================================================
# 第二部分：DNA分析与仿写方案推荐
# ===========================================================================

# --- 方案推荐（Agent 分析源小说DNA后，给用户推荐的多层次改编方案） ---

ADAPTATION_PROPOSALS = """## 《神秘之旅》仿写方案推荐

基于源小说前两章的DNA分析（穿越+属性面板金手指+贵族学院弱者逆袭），
提出以下4个不同改编距离的方案供选择：

---

### 方案S+（推荐）：同世界观 · 换性别 + 情绪炼金金手指

**改编距离**: 最近，DNA保留度最高

| 维度 | 原作 | 仿写 |
|-----|------|------|
| 主角 | 罗靖/加隆（男，16岁，触电穿越） | 林夕/艾琳（女，16岁，实验室事故穿越） |
| 家庭 | 重组家庭，父亲隆巴尔+非血缘妹妹瑛儿 | 重组家庭，母亲梅瑟尔+非血缘弟弟里昂 |
| 职业 | 父母-橡胶公司职员 | 母亲-制药公司职员 |
| 学校 | 圣莺贵族学院（排名第三） | 银枫贵族学院（排名第五） |
| 金手指 | 属性面板（力量/敏捷/体质/智力/潜能） | 情绪炼金（看到情绪雾气→采集晶体→炼化增强→融合永久能力） |
| 触发方式 | 买古董→获取能量 | 接近情绪波动强烈的人→看到情绪雾气→物理接触采集晶体 |
| 变强维度 | 身体属性加点（力量/敏捷） | 情绪对应能力（愤怒→爆发力/恐惧→感知力/爱→治愈力/野心→意志力） |
| 限制代价 | 需要钱买古董 | 被采集者情感枯竭+情绪反噬+晶体褪色+感知过载 |

**推荐理由**: 性别翻转+全新金手指机制。原作是"RPG加点"，情绪炼金是"炼金术"——从感知他人情绪→采集晶体→炼化获能，
体验完全不同。女主视角天然适合"情绪洞察"型金手指，学院=青春期情绪金矿。

**场景转换示例**:
- 原: 罗靖触电→穿越加隆 ➜ 仿: 林夕触碰感知矩阵→穿越艾琳
- 原: 校车上看到两个帅气男生→自卑 ➜ 仿: 校车上看到两个出众女生→注意到她们身上的浅紫色雾气
- 原: 视野浮现五个红色属性符号→念出数值 ➜ 仿: 看到里昂肩上暗金色雾气→触碰凝出晶体→暖流沁入→里昂表情微微变淡

---

### 方案S：同世界观 · 同性别 · 命运赌局金手指

**改编距离**: 近，仅改金手指实现

| 维度 | 原作 | 仿写 |
|-----|------|------|
| 主角 | 罗靖/加隆（男，16岁） | 陈默/雷恩（男，16岁） |
| 家庭 | 重组家庭 | 重组家庭（结构不变） |
| 金手指 | 属性面板（收集资源→数值加点） | 命运赌局（与他人对赌命运→赢取筹码→兑换能力） |
| 触发方式 | 买古董获取能量 | 向目标发起"赌约"，双方各押筹码，结果由命运裁定 |
| 变强维度 | 身体属性加点 | 赢取的筹码可兑换：体能强化/技能领悟/运气加成/命运窥视 |
| 限制代价 | 需要钱 | 输了会失去已有筹码；对赌次数有冷却期；押注越大风险越大 |

**推荐理由**: 保留男性主角视角，"对赌"机制与"加点"完全不同——每次变强都是一场博弈，有输有赢的不确定性。

**场景转换示例**:
- 原: 视野浮现属性面板 ➜ 仿: 眼前浮现命运赌桌的虚影，上面写着"请选择你的赌注"
- 原: "力量0.31，敏捷0.22..." ➜ 仿: "当前筹码：3枚。可发起赌约，也可兑换能力。"

---

### 方案A：换世界观 · 辐射脉搏金手指

**改编距离**: 中等，世界观大改但骨架不变

| 维度 | 原作 | 仿写 |
|-----|------|------|
| 世界观 | 类欧洲工业革命异世界 | 末世废土（核战后300年） |
| 主角 | 穿越到贵族学院学生 | 穿越到废土生存学校学员 |
| 家庭 | 橡胶公司普通职员家庭 | 避难所物资回收员家庭 |
| 学校 | 圣莺贵族学院 | 钢骨堡垒生存学校 |
| 金手指 | 属性面板（加点） | 辐射脉搏（吸收环境辐射→心跳共振→脉搏频率解锁不同能力层级） |
| 触发方式 | 买古董 | 靠近辐射源时心脏自动共振吸收，辐射越强吸收越多 |
| 变强维度 | 身体属性 | 脉搏频率对应能力：低频→体质强化/中频→感官增幅/高频→细胞再生/超频→短暂变异 |
| 限制代价 | 需要钱买古董 | 吸收过量会心脏过载；高辐射区危险；变异有失控风险 |
| 社会矛盾 | 贫困生vs富家子弟 | 平民区学员vs核心区精英 |

**推荐理由**: 末世废土自带紧张氛围，"辐射脉搏"以心跳为载体，体感强烈。
"贫困生在精英学校"的核心DNA完美迁移为"平民区学员在核心区学校"。

**场景转换示例**:
- 原: 干净的灰白街道+欧式建筑 ➜ 仿: 锈迹斑驳的废墟走廊+加固掩体建筑
- 原: 校车接送 ➜ 仿: 装甲运输车穿越辐射区
- 原: 视野浮现属性面板 ➜ 仿: 心脏突然剧烈跳动，感觉到周围辐射在向自己涌来

---

### 方案B：现代都市 · 契约便签金手指

**改编距离**: 远，题材跨越但核心DNA保留

| 维度 | 原作 | 仿写 |
|-----|------|------|
| 世界观 | 异世界奇幻 | 现代都市（表面正常，暗藏超能者） |
| 主角 | 罗靖穿越到异世界 | 苏然"觉醒"后发现世界真相 |
| 学校 | 圣莺贵族学院（明面） | 启明中学（表面普通，实为超能者筛选学校） |
| 金手指 | 属性面板（加点） | 契约便签（写下契约内容→满足条件后自动兑现效果） |
| 触发方式 | 买古董 | 在特殊便签纸上写下契约条款，签名生效 |
| 变强维度 | 身体属性 | 契约效果无限制，但条件越苛刻效果越强（"连续跑步30天"→获得超常耐力） |
| 限制代价 | 需要钱 | 违约会受到反噬；便签数量有限（每周只能写1张）；条件必须自己完成 |
| 家庭 | 重组家庭+贫困 | 单亲+打工家庭 |
| 核心矛盾 | 贫困生vs富家子弟 | 普通觉醒者vs世家传承者 |

**推荐理由**: 都市背景降低读者门槛，"契约便签"机制将变强过程变成自我挑战——
不是收集外部资源，而是给自己设定目标并完成。弱者逆袭DNA完美保留。

**场景转换示例**:
- 原: 穿越到异世界 ➜ 仿: 车祸后"觉醒"，口袋里多了一叠奇怪的便签纸
- 原: 属性面板浮现 ➜ 仿: 便签纸上自动浮现文字："写下你的第一份契约"
- 原: 校车上观察同学 ➜ 仿: 校车上注意到几个同学口袋里也有类似的便签纸
"""

# --- 预定义的仿写方案内容（以用户选择 S+ 方案为例） ---

DNA_ANALYSIS = """## 《神秘之旅》文风DNA分析

### 1. 叙事视角与文风
- **视角**: 第三人称限制视角，紧跟主角加隆
- **句式**: 短句为主，动作描写简洁有力，拟声词频繁（轰隆、嘭、咔嚓）
- **节奏**: 开篇即用连续短句制造紧迫感，穿插意识流内心独白
- **描写密度**: 中等偏低，重动作轻环境，环境描写点到为止

### 2. 结构DNA
- **开篇模式**: 触电穿越 → 意识混沌 → 记忆融合 → 适应新身份
- **信息投放**: 通过主角整理记忆来投放世界观（类欧洲工业革命+异世界要素）
- **章节结构**: 每章3500-4000字，场景切换1-2次
- **爽点节奏**: 第1章铺设悬念，第2章末尾出金手指（属性面板）

### 3. 金手指结构DNA
- **类型**: 游戏化属性面板（力量/敏捷/体质/智力/潜能）
- **获取方式**: 穿越附赠，触电变异灵魂产生
- **成长机制**: 潜能值积累→分配四维属性
- **初始值**: 极低（0.2-0.3级别），主角起点很低

### 4. 角色生态
- **主角特征**: 普通→穿越→获得金手指，起点低、身体虚弱、成绩中下
- **家庭设定**: 重组家庭，父母普通职员，经济拮据但供贵族学院
- **妹妹角色**: 非血缘妹妹瑛儿，性格沉默寡言，关系一般
- **社会环境**: 贵族学院中的贫困生，自卑感驱动成长
"""

CHARACTER_MAPPING = """## 角色映射表（S+方案：同世界观，换性别+金手指）

| 原作角色 | 仿写角色 | 变化说明 |
|---------|---------|---------|
| 罗靖/加隆（男，16岁） | 林夕/艾琳（女，16岁） | 性别转换，保留普通家庭+穿越设定 |
| 瑛儿（妹妹，非血缘） | 里昂（弟弟，非血缘） | 性别对调，沉默内向→冷淡守护型 |
| 隆巴尔（父亲） | 梅瑟尔（母亲） | 单亲母亲，橡胶公司→制药公司职员 |
| 圣莺学院 | 银枫学院 | 同类贵族学院，排名第五 |
| 属性面板（力量/敏捷/体质/智力/潜能） | 情绪炼金（雾气感知→晶体采集→炼化增强→融合能力） | 机制完全不同：原作是"数值加点"，仿写是"炼金术"——采集他人情绪晶体获得对应能力 |

### 金手指机制对比
| 维度 | 原作（属性面板） | 仿写（情绪炼金） |
|-----|----------------|-----------------|
| 触发 | 买古董→获取能量 | 接近情绪波动强烈的人→看到情绪雾气 |
| 资源 | 能量值（数字） | 情绪晶体（彩色实体，每种颜色=一种情绪） |
| 采集条件 | 花钱买下古董即可 | 对方必须正在经历该情绪且波动剧烈+物理接触 |
| 品质分级 | 古董越贵能量越多 | 越厉害的人产出的晶体品质越高（浑浊/通透/完美） |
| 成长方式 | 选属性加点 | 炼化晶体获临时增强/组合不同晶体获永久能力 |
| 负面影响 | 无 | 被采集者出现情绪变淡、情感空白、情感麻木 |
"""

POWER_SYSTEM = """## 新金手指设计：情绪炼金

### 一、情绪来源与晶体类型
| 情绪来源 | 触发场景举例 | 晶体颜色 | 炼化后增强效果 |
|---------|------------|---------|-------------|
| 怒（愤怒/不甘/屈辱） | 被人羞辱、遭遇不公、竞争失败 | 赤红色 | 爆发力、力量激增 |
| 哀（悲伤/恐惧/绝望） | 亲人离别、考试失败、面对危险 | 墨黑色 | 感知增强、危险预判 |
| 喜（喜悦/兴奋/自信） | 取得成就、恋爱心动、被认可 | 金色 | 敏捷、反应加速 |
| 爱（亲情/关爱/牵挂） | 母亲送别、兄弟守护、朋友关心 | 暗金色 | 治愈、身体恢复 |
| 欲（野心/嫉妒/渴望） | 争夺名次、觊觎权力、不服输 | 深紫色 | 意志力、精神韧性 |

### 二、采集条件（严格）
1. **当前正在经历**：对方必须正在体验该情绪，过去的情绪无法采集
2. **波动足够强烈**：平静状态的人身上雾气极淡，只有情绪剧烈波动时雾气才浓郁到可以采集
3. **物理接触**：必须触碰到对方（握手、拍肩、碰袖子），隔空无法采集
4. **距离限制**：初期只能感知3米内的情绪雾气

### 三、晶体品质分级
| 来源 | 品质 | 表现 | 炼化效果 |
|-----|------|------|---------|
| 普通同学 | 浑浊级 | 小而浑浊，颜色暗淡 | 临时增强弱（5分钟） |
| 学院教官 | 通透级 | 中等大小，晶莹通透 | 临时增强明显（15分钟） |
| 校长/将军级强者 | 完美级 | 大而璀璨，色泽完美 | 增强效果强（30分钟），可用于融合 |

### 四、被采集者的负面影响
| 采集程度 | 对被采集者的影响 | 恢复时间 |
|---------|----------------|---------|
| 轻度（偶尔一次） | 情绪变淡——正在生气的人忽然觉得"算了" | 几小时 |
| 中度（一天多次） | 情感空白——对事物暂时提不起兴趣 | 1-2天 |
| 重度（反复同一人） | 情感麻木——对该类情绪的感受力永久下降 | 难以恢复 |

### 五、成长阶段
| 阶段 | 能力 | 条件 |
|-----|------|------|
| 感知期 | 只能看到雾气，偶尔能凝出浑浊小晶体 | 初始状态 |
| 采集期 | 稳定凝晶，能炼化获得临时增强 | 累计采集10+颗晶体 |
| 融合期 | 可以组合不同类型晶体，获得永久能力 | 同时拥有3种以上类型的通透级晶体 |
| 觉醒期 | 自身情绪自动结晶，不再依赖他人 | 完成至少3次成功融合 |
| 超越期 | 可以创造自然界不存在的新情绪和新能力 | 觉醒后的终极进化 |

### 六、限制与代价
1. 来源限制：必须有人正在经历强烈情绪波动，平静环境=无资源
2. 道德代价：被采集者会受到负面影响，频繁采集会伤害身边的人
3. 情绪反噬：炼化晶体时会短暂体验该情绪，炼化太多同类会导致情绪失控
4. 晶体褪色：采集的晶体不能无限储存，放置过久会褪色失效
5. 感知过载：人多的地方雾气密集，长时间暴露会导致头痛、眩晕
6. 自身盲区：初期无法采集自己的情绪（觉醒前的关键限制）

### 获取方式
- 穿越变异：实验室事故中触碰高能感知矩阵，灵魂层面产生变异，获得感知情绪雾气的能力
"""

WORLD_SETTING = """## 世界观设定（S+方案）

## 社会结构
亚路联邦采用贵族议会制，贵族占据社会上层，掌控学院、军队和资源分配。普通平民通过学院选拔可获得晋升机会。银枫学院是排名第五的贵族学院，招收少量平民子弟。

## 能力体系规则
异世界拥有"感知力"体系，少数人天生能感知到微弱的情绪能量场。正统修炼通过冥想和药剂增强感知力，情绪炼金术是被遗忘的古老分支。

## 资源与经济
制药工业是亚路联邦的支柱产业，梅瑟尔在一家中型制药公司任职。情绪晶体在黑市上价值极高，但大多数人不知道其存在。

## 地理与空间
银枫城位于联邦中部，以巨大的银枫树林闻名。银枫学院坐落在城市北区的山丘上。

## 势力格局
威斯曼帝国与亚路联邦长期对峙，银枫学院内部分为贵族派和实力派。

## 隐藏设定与未解之谜
情绪炼金术曾是古代文明的核心技术，但在千年前被禁止。银枫学院地下据传藏有古代遗迹。
"""

ADAPTATION_PLAN = json.dumps(
    [
        {
            "chapter": 1,
            "source_title": "第一卷 初始 1",
            "adapted_title": "觉醒",
            "scene_mapping": [
                {
                    "source": "罗靖触电身亡→意识穿越→在马车上昏迷醒来",
                    "adapted": "林夕实验室事故→意识穿越→在出租马车上昏迷醒来",
                },
                {
                    "source": "发现自己是加隆→整理记忆→了解世界观",
                    "adapted": "发现自己是艾琳→整理记忆→了解世界观（制药公司家庭）",
                },
                {
                    "source": "家庭早餐场景→父亲叮嘱学业→兄妹互动",
                    "adapted": "家庭早餐场景→母亲叮嘱学业→姐弟互动",
                },
            ],
            "key_elements": "开篇短句拟声词节奏、穿越意识流、记忆融合信息投放、家庭日常细节",
            "word_count_target": "3500-4000字",
        },
        {
            "chapter": 2,
            "source_title": "2",
            "adapted_title": "银枫学院",
            "scene_mapping": [
                {
                    "source": "校车上的兄妹对话→观察优秀男生→自卑对比",
                    "adapted": "校车上的姐弟对话→观察优秀女生→注意到她们身上浅紫色雾气",
                },
                {
                    "source": "金手指浮现→五个属性符号出现→念出数值",
                    "adapted": "情绪雾气初现→看到里昂暗金色雾气→触碰弟弟凝出暗金晶体+弟弟语气变冷",
                },
                {
                    "source": "到达学院→描写校园建筑→进入教室",
                    "adapted": "到达学院→密集人群雾气导致头痛→进教室注意到里昂态度微妙变化",
                },
            ],
            "key_elements": "校车场景的微妙人际、情绪炼金揭示的节奏控制、采集后果伏笔",
            "word_count_target": "3500-4000字",
        },
    ],
    ensure_ascii=False,
    indent=2,
)

# --- 预定义的仿写章节内容 ---

CHAPTER_1_CONTENT = """    嗞啦！！

    林夕的大脑剧烈震颤起来。

    嗞嗞嗞啦！！

    林夕的大脑像是被无数根针同时刺穿。

    她在颤抖！她的意识在崩塌！！

    啪！！

    后脑勺猛地撞在一块坚硬的什么东西上，林夕闷哼了一声。

    勉强睁开双眼，她的视野里是一片摇晃的昏暗。一个模糊的人影坐在对面，正低着头翻看着什么，马车外传来辘辘的车轮声和偶尔的马蹄声。人影左侧的小窗帘被风掀开一角，窗外刷的一道闪电劈过，把整个车厢照得惨白。

    唔……

    林夕呻吟了一声，她想抬手揉揉胀痛的太阳穴，但全身像是泡在冰水里一样完全不听使唤，四肢充斥着麻木与刺痛的奇怪混合感，就像四根被冻僵的枯枝。

    "我死了？"她脑子里还是一团糨糊。最后的记忆是在大学实验室里，她不小心碰到了那台实验中的高能感知矩阵装置，指尖触碰金属探头的瞬间，一团刺眼的白光在眼前炸开，然后是焦糊味和尖锐的警报声，然后就什么都不知道了。

    意识混沌得厉害，所有记忆像是被搅碎的拼图。

    林夕拼命睁大眼睛，想看清周围到底是什么情况。

    咯噔！

    马车猛地一颠，她的后脑再次撞上车壁，一阵尖锐的疼痛炸开，林夕彻底昏了过去。

    不知道过了多久。也许是半天，也许是好几天。

    她终于感觉到四肢有了一丝微弱的知觉，意识像是从深水中缓缓浮上来。

    吱呀。一声轻响，像是门被推开的声音。

    "妈妈出去了吗？"一个少年的声音在问。

    "嗯，她一早就出门了，去药铺拿点草药回来。你照顾好你姐。"一个女人疲惫的声音回答，然后是渐远的脚步声。

    林夕猛然发现自己正坐在一间狭小但整洁的房间里，面前是一张原木色的书桌，右手还握着一支蘸水笔，笔尖的墨迹正在白纸上慢慢洇开。

    窗外透进来灰蒙蒙的光，外面淅淅沥沥的下着雨，对面那栋灰白色建筑的屋顶上水珠闪烁。

    忽然间，如同决堤的洪水，一股庞大而陌生的记忆洪流猛地灌入她的脑海。

    "唔……"她不由得低声呻吟，双手捂住额头。无数不属于她的记忆疯狂涌入大脑。

    艾琳？我是艾琳？我……穿越了？

    她顾不得头痛欲裂，强忍着剧烈的眩晕，飞速浏览涌入脑海的这些记忆。

    这个世界的背景类似于欧洲工业革命时期。有了蒸汽机车和简陋的汽车，有了步枪和野战炮，但还没发展出大规模杀伤性武器。

    她现在的身份是一个叫艾琳的普通家庭女孩，今年十六岁，母亲梅瑟尔是格莱恩制药公司的普通职员，独自抚养她和一个叫里昂的弟弟。里昂是母亲再婚后丈夫带来的孩子，两人没有血缘关系。生活环境是工业革命风格的异世界——没有中国美国，最强的三个国家叫亚路联邦、威斯曼帝国和郁金香共和国。

    异世界的特征很明显——艾琳和里昂都是天生的银灰色头发，琥珀色的眼睛。发色随母亲，瞳色随已故的生父。这种组合在地球上绝不存在。

    从小学到中学到大学，这个世界的教育体系和地球惊人地相似。艾琳就读的是本省排名第五的银枫贵族学院，高中部，入学一年。现在是假期，她在家突发高烧，原本的艾琳就这么没了，穿越过来的林夕恰好接了盘。

    一边整理记忆，一边恍惚间不知怎么就换好了衣服。等她回过神来，自己已经坐在一间小小的白色餐厅里，面前是一块切成三角形的杏仁蛋糕，淡黄色的糕体上铺着一层薄薄的糖霜，点缀着几颗红色的蔓越莓干。

    林夕的注意力还大半沉浸在艾琳留下的记忆里。

    记忆中，艾琳和里昂虽然都在贵族学院就读，但这完全是母亲节衣缩食、加班加点勉强撑起来的。为了两个孩子的学费，家里的一切开销都压缩到了最低，母亲连件新衣服都舍不得买，制药公司的全部奖金和加班费统统变成了学院的学费和生活费。

    可惜姐弟俩的成绩都不怎么样，始终在中下游徘徊，怎么努力也上不去。更糟糕的是，银枫学院里大多数学生非富即贵，和他们一比，艾琳家的条件差得太远。这种落差日复一日地侵蚀着两个孩子——艾琳变得敏感而小心翼翼，里昂则变得沉默冷淡，不爱和人打交道。

    "马上就要回学校了，在学校好好学习，别和同学闹矛盾。"母亲梅瑟尔坐在对面，一边喝着黑咖啡一边低声叮嘱，"里昂也是，别老一个人待着，多交几个朋友。"

    "知道了。"里昂简短地应了一声。他坐在林夕右手边，穿着熨烫整齐的白色衬衫校服，胸口别着银枫学院的校徽——一片银色枫叶环绕着拉丁字母。下身是修身的黑色长裤配皮鞋。少年面容清秀但表情淡漠，银灰色的头发整齐地梳向一侧。

    林夕默不作声地低头吃着蛋糕，端起手边的热牛奶抿了一口。她扫了一眼自己的装束：白色束腰上衣，袖口和领口缀着银灰色的细纹装饰，下身是黑紫色百褶裙配厚厚的黑色连裤袜和小皮鞋。胸前同样别着银枫学院的银叶校徽。

    她抬头看了看餐桌对面墙上挂着的小镜子——银灰色的长发有些凌乱，琥珀色的眼睛下方有明显的黑眼圈，脸色苍白，嘴唇也没什么血色。刚从高烧中恢复的身体还虚弱得厉害。

    直到吃完早餐，林夕才勉强消化了艾琳大半的记忆。姐弟俩帮着收拾了餐具，各自回房间整理上学的行李。

    "姐，你看到我的地理课本没？"里昂在隔壁房间里问。

    "没看到。"林夕——不，现在应该叫艾琳了——随口回了句。

    她自己也在手忙脚乱地收拾书本。历史、地理、礼仪、数学，还有什么剑术和弓术……科目多得离谱，比地球的高中还多好几门。把一堆课本塞进黑色书包，艾琳轻轻叹了口气，慢慢走到窗前，推开窗户，一股凉爽的湿润空气扑面而来。

    窗外往下看，是两栋居民楼之间的小广场，灰色的方砖地面被雨水打得发亮。广场左侧，几个人正在一个举着标语牌的壮汉面前排队，人越聚越多。标语上写着"科林斯必胜"。

    楼下门口，一个头巾妇女正推着一辆木头手推车骨碌碌地出来，车上摆满了煎饼摊的锅碗瓢盆。

    呼——一只灰白色的鸟从艾琳眼前掠过，转了两个弯就消失了。

    她怔怔地回过神来。这一刻她才真正意识到——自己是真的到了另一个世界。她站在四楼的窗前，俯瞰着一个和中国截然不同的城市。

    街上的行人，金发银发红发都有，各种肤色各种眼睛颜色，用的是一种类似英语的语言。有了艾琳的记忆，她自然能听能看能说。

    现在的她，已经不是地球上那个二十二岁的大学生了，而是一个十六岁的普通女孩，有着普通的家庭，普通的背景长相，还有一副虚弱不堪的身体。

    "如果不是这具身体本来就虚弱，我的灵魂说不定根本进不来。"艾琳无奈地苦笑了一下。她隐隐有种预感，之前在马车上昏迷的那段时间，多半就是原本的身体在本能地抵抗外来意识的入侵。要是换一个更强壮的身体，她大概会被直接弹出去。

    "根据记忆里的知识，这个世界应该处于工业革命中期，有了基础的热武器，但还没出现决定性的战略武器。跟核弹和导弹出现之前的地球格局差不多。"她仔细梳理着脑中的信息，"完全不是什么魔法斗气修仙的世界，连一点超自然的迹象都没有。"

    想到这里，她自己都不知道该怎么往下活了。刚意识到穿越的时候还多少有点期待，以为会有什么金手指或者特殊能力，结果仔细整理了一遍，这就是个落后版本的科技世界。

    "算了，走一步看一步吧。当务之急是把这具身体调养好。"艾琳抬起纤细的手臂，瘦得简直像根竹竿，皮肤白得近乎透明，手腕上青色的血管清晰可见。她不由得又叹了口气。

    提着书包，姐弟俩一前一后走到家门口。艾琳手里拎着垃圾袋走在前面，顺着楼梯间往下走。一边走，她也在一边打量着这栋居民楼里的其他住户和这个时代的生活细节。

    楼梯间有些昏暗，每层只住两户人家，各家门左侧都挂着刻着名字的黄铜信箱，看上去都有些年头了。

    上上下下进出的住户，大多穿着体面的西装或长裙，一个个腰杆挺得笔直。虽然脸上或多或少带着疲色，但步伐都很匆匆忙忙，显得生活节奏极快。只有极少数几个住户看起来条件较差，还有租住在这里的小贩之类。

    姐弟俩一直走到楼下都没怎么说话。丢掉手里的垃圾，艾琳看了一眼站在身旁的里昂——他比她矮了大半个头，面容清秀但总是一副冷淡的表情。他是母亲再婚后带过来的孩子，和她没有血缘关系。两人的关系也就比普通朋友好那么一点点。

    和往常一样，两人上了学院接送的大巴车，车上已经稀稀疏疏坐了一些学生。"""

CHAPTER_1_SUMMARY = """林夕（原地球大学生）在实验室事故中触碰高能感知矩阵装置后意识穿越，\
灵魂进入异世界少女艾琳的身体。艾琳是银枫贵族学院高一学生，母亲梅瑟尔是制药公司职员，\
有一个无血缘关系的弟弟里昂。家境拮据但供两个孩子读贵族学院。\
艾琳因高烧死亡后被林夕的灵魂接替。\
世界观为类欧洲工业革命异世界（亚路联邦、威斯曼帝国、郁金香共和国三大国）。"""

CHAPTER_2_CONTENT = """    艾琳和里昂在校车后排找了个位置坐下。她扫了一眼前面的学生，清一色的银枫学院校服——女生白色束腰上衣加百褶裙和黑丝袜，男生白衬衫加黑长裤，整齐得像是复制粘贴。

    学生们三三两两聚在一起，笑声和聊天声此起彼伏。

    车子又停了几次，陆陆续续上来更多学生。很快，两个容貌出众的女生有说有笑地上了车——一个高挑优雅，一头金色长发如瀑布般垂在肩后；另一个小巧玲珑却气场十足，一看就是那种从小被精心养育的大家闺秀。两人一上车，周围不少男生的目光都有意无意地投了过去。

    艾琳坐在里昂旁边，注意到弟弟的视线也不自觉地在那两个女生身上停了一瞬。她低头看了看自己苍白的手背和微微发抖的指尖，无奈地摇了摇头，移开了目光。

    像她这样坐在角落里不起眼的普通女生，车上实在太多了。在那两位出众女生的映衬下，她连背景板都算不上。

    艾琳侧过脸看着车窗外飞掠而过的街景。灰白色的街道两侧排列着黑色铸铁路灯，路边的建筑大多是普通的水泥楼房，偶尔能看到一些带有石雕装饰的白色建筑。风格有些像欧式，但细节上又处处透着异世界的味道。不时有蒸汽汽车从旁边轰隆隆地超过去。

    "妈让我转告你，下周不用赶回家，就在学校吃，"身旁的里昂忽然低声开口，"公司有个紧急项目需要她出差，可能一整个星期都回不来。"

    "哦，知道了。"艾琳点点头，尽量模仿原主的语气。"对了，上次期末你名次进步了好几名，妈是不是给你买了那个……模型？"

    "那又怎样？"里昂偏过头不理她，"你要是成绩上去了，妈也会给你买东西的。"

    艾琳笑了笑，没再说什么。

    就在这时，她忽然发现了异常。

    里昂的肩膀周围，正浮动着一层淡淡的暗金色雾气。

    那雾气很轻很薄，像是被阳光照亮的微尘，缓缓地绕着里昂的肩头和手臂流转。它不是从外面来的——而是从里昂的身体里，一丝一丝地渗出来。

    艾琳的瞳孔猛地收缩了一下。

    她下意识地转头看向前排——那两个容貌出众的女生身上也有雾气，但颜色完全不同，是浅紫色的，比里昂的淡得多，几乎透明，像是随时都会消散的薄纱。

    再往后看。后排角落里，一个黑发男生正压低声音和旁边的人争论着什么，脸涨得通红。他的身上翻涌着一团浓烈的赤红色雾气，比车上任何人的都要浓郁刺眼，像是一簇正在燃烧的暗火。

    "这……这是什么？"艾琳的心跳陡然加速。她又飞快地扫了一圈车厢里的其他学生——每个人身上或多或少都有雾气，只是大多数人的雾气极淡极淡，几乎看不出颜色。只有那些正在说笑、生气或者情绪明显的学生，身上的雾气才稍微浓一些。

    没有人注意到她的异样。该聊天的继续聊天，该看书的继续看书。

    "穿越福利……吗？"艾琳的声音在喉咙里颤了一下。她看过不少穿越小说，知道通常会带点什么特殊能力，但她还以为自己是那种倒霉的纯白板穿越，没想到此刻才显出端倪。

    里昂已经从书包里掏出一本历史教材，正低着头默默翻看。那层暗金色的雾气依然在他肩头流转，柔和而温润。艾琳盯着它看了好一会儿，心里涌上一种说不清的感觉——那雾气让她觉得安心，好像在无声地诉说着什么。

    她不自觉地伸出手，轻轻碰了碰里昂的袖子。

    指尖触碰到布料的刹那——一阵凉意从指腹蔓延开来，像是把手指浸入了冰凉的溪水。紧接着，她感觉到有什么东西在指尖凝结，从里昂肩膀上的暗金色雾气中，被一丝丝抽出来，汇聚在她的掌心。

    一颗温润的暗金色小晶体，如同一滴凝固的琥珀，安静地躺在她的手心里。

    还没来得及细看，那颗晶体就像融化的冰一样沁入了她的皮肤。

    一股暖流瞬间从掌心扩散到全身——那种感觉就像寒冬腊月里喝了一口滚烫的热汤，从胃一直暖到四肢百骸。她忽然觉得无比安心、无比踏实，好像被一双无形的手轻轻拥住了肩膀。

    暖流在体内流转了几秒，然后慢慢消退。但那种安心的余韵还残留在胸口，久久不散。

    艾琳怔住了。

    她低头看了看自己的手掌——掌心空空的，什么都没有，但皮肤上还残留着一丝暖意。

    "姐，你拉我袖子干嘛？"里昂偏过头看了她一眼。

    艾琳注意到一件微妙的事——里昂说话的语气，比刚才冷了一点点。刚才转达母亲出差的消息时，虽然也是简短的句子，但能感觉到一丝对姐姐的关心在里面。而现在这句话，纯粹是疑惑，没有多余的温度。

    而且，他肩膀上那层暗金色的雾气，好像也比刚才淡了一些。

    "没……没什么，手滑了。"艾琳连忙缩回手，心脏砰砰跳个不停。

    里昂看了她一眼，没有追问，重新低头翻书。但他翻书的动作明显比刚才快了几分，像是在敷衍着什么。

    校车忽然停了下来。

    "到了到了，都下车！"司机是个留着大胡子的壮汉，扭过身大声吆喝。

    学生们开始陆陆续续地往下走。里昂收起课本，拎着书包径直下了车，甚至没有像往常那样拍拍艾琳的肩膀提醒她。

    艾琳愣了一下，连忙拎起书包跟上。

    车外是一大片修剪整齐的椭圆形草坪，翠绿的草地边缘停着一排排黑色校车，学生们如白色潮水般从各辆车上涌出。

    草坪尽头，一片银灰色主调的建筑群巍然矗立。中央是一栋方形圆顶的主楼，正门上方的石雕枫叶校徽在阴天的光线下泛着暗银色的光泽。两侧是对称的高塔，少说也有十几层。

    然而艾琳此刻根本无暇欣赏校园风景。

    数百名学生从各辆校车上涌出，密密麻麻的人群——每个人身上的雾气在她视野里同时炸开。各种颜色的雾气层层叠叠地交织在一起，赤红、暗金、浅紫、墨黑、金色……整个草坪上空仿佛漂浮着一层绚烂的薄雾。

    太阳穴猛地一阵刺痛。

    "唔……"艾琳用力按住额角，皱起了眉头。那些雾气的色彩太过密集了，像是有人往她的视网膜上同时投射了几百个不同频率的光源，大脑根本处理不过来。

    她不得不低下头，盯着地面上自己的鞋尖，勉强跟着人流往前走。只要不直视人群，头痛就会缓解一些。

    "嘿，别堵路！"一个高个子男生从后面催促。

    艾琳连忙加快脚步。

    她注意到里昂已经不知什么时候走到了前面，正和一个同样沉默寡言的男生并肩走着，两人之间没有任何交谈。但和往常不同的是，里昂的步伐似乎比平时快了一些，像是刻意和她拉开了距离。

    走进校区主楼的大厅，室内的人群密度比外面稍微低了一些，头痛也减轻了不少。高挑的穹顶上绘着银色枫叶的纹章，大理石地面被无数双皮鞋踩得铮亮。两侧的走廊延伸向不同的教学区，墙上挂着历届优秀毕业生的画像和学院历史的铭牌。

    "艾琳是第一校区高一三班的……"她循着记忆，快步跟上人群，走进校区左侧的一栋梯形教学楼。

    二楼走廊尽头，挂着"高一三班"黄铜铭牌的教室门半开着，里面已经坐了不少学生。艾琳深吸一口气，推门走了进去。

    教室不算大，大约容纳四十人左右。课桌排列整齐，靠窗的几个好位置早就被几个衣着光鲜的学生占据了。艾琳循着记忆找到了自己的座位——靠墙倒数第二排，角落里一个最不起眼的位置。

    坐下后，她把书包放在桌上，偷偷张开手掌——空空的，但掌心残留的暖意不像幻觉。

    而且她注意到一件事：里昂进教室的时候从她身边走过，连看都没看她一眼。明明在家里吃早餐时还会搭两句话，在校车前半段也主动帮忙转达妈妈的消息……但自从她碰了他袖子之后，里昂对她的态度就冷了一截。

    "难道……和刚才有关？"艾琳握紧了拳头，心里隐隐升起一丝不安。"""

CHAPTER_2_SUMMARY = """艾琳和里昂乘校车前往银枫学院。车上观察到贵族学院的阶层差距——\
两个出众女生上车引来关注，艾琳感到自卑。姐弟对话中得知母亲即将出差。\
关键转折：艾琳突然能看到人身上的彩色雾气——里昂肩上暗金色（关爱）、\
前排女生浅紫色（优越感）、后排吵架男生赤红色（愤怒）。\
她无意中触碰里昂袖子，指尖凝出一颗暗金色晶体，沁入皮肤后感到一阵暖流。\
但采集后里昂的态度明显变冷，语气少了温度，甚至不再主动提醒她下车。\
到达银枫学院时，密集人群的雾气导致太阳穴剧痛。进入高一三班教室后，\
掌心暖意残留，但里昂走过身边连看都没看她——采集似乎有未知的代价。"""


class TestAdaptationProposals:
    """测试仿写方案推荐的保存与结构验证。"""

    def test_save_proposals(self, shenmi_project):
        """应成功保存方案推荐。"""
        result = save_analysis.invoke(
            {"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS}
        )
        assert "保存成功" in result

    def test_proposals_exported_to_file(self, shenmi_project):
        """方案推荐应导出到analysis/目录。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        export_file = shenmi_project / "analysis" / "adaptation_proposals.md"
        assert export_file.exists()
        text = export_file.read_text(encoding="utf-8")
        assert "仿写方案推荐" in text

    def test_proposals_contain_four_plans(self, shenmi_project):
        """应包含4个不同距离的改编方案。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        assert "方案S+" in result
        assert "方案S" in result
        assert "方案A" in result
        assert "方案B" in result

    def test_splus_proposal_gender_swap(self, shenmi_project):
        """S+方案应包含性别翻转+情绪炼金金手指。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        # S+方案核心：性别翻转+情绪炼金金手指
        assert "林夕/艾琳（女" in result
        assert "情绪炼金" in result

    def test_s_proposal_fate_gambit(self, shenmi_project):
        """S方案应包含命运赌局金手指。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        assert "命运赌局" in result
        assert "筹码" in result

    def test_a_proposal_wasteland(self, shenmi_project):
        """A方案应包含末世废土+辐射脉搏。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        assert "末世废土" in result
        assert "辐射脉搏" in result

    def test_b_proposal_modern_city(self, shenmi_project):
        """B方案应包含现代都市+契约便签。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        assert "现代都市" in result
        assert "契约便签" in result

    def test_all_proposals_have_scene_examples(self, shenmi_project):
        """每个方案都应有场景转换示例。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        # 每个方案都有场景转换示例（原➜仿），共4个方案
        assert result.count("➜") >= 10  # 4个方案共10+个转换示例

    def test_all_proposals_preserve_core_dna(self, shenmi_project):
        """所有方案都应保留核心DNA（弱者逆袭+独特金手指+学院设定）。"""
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})
        result = get_analysis.invoke({"key": "adaptation_proposals"})
        # S+: 银枫贵族学院, S: 同结构, A: 钢骨堡垒生存学校, B: 启明中学
        assert "学院" in result or "学校" in result or "中学" in result
        # 所有方案都有独特金手指系统
        for keyword in ["情绪炼金", "命运赌局", "辐射脉搏", "契约便签"]:
            assert keyword in result


class TestDnaAnalysis:
    """测试DNA分析方案的保存与检索。"""

    def test_save_dna_analysis(self, shenmi_project):
        """应成功保存DNA分析。"""
        result = save_analysis.invoke({"key": "dna_analysis", "content": DNA_ANALYSIS})
        assert "保存成功" in result

    def test_retrieve_dna_analysis(self, shenmi_project):
        """应能检索DNA分析内容。"""
        save_analysis.invoke({"key": "dna_analysis", "content": DNA_ANALYSIS})
        result = get_analysis.invoke({"key": "dna_analysis"})
        assert "短句为主" in result
        assert "拟声词" in result
        assert "属性面板" in result

    def test_dna_exported_to_file(self, shenmi_project):
        """DNA分析应导出到analysis/目录。"""
        save_analysis.invoke({"key": "dna_analysis", "content": DNA_ANALYSIS})
        export_file = shenmi_project / "analysis" / "dna_analysis.md"
        assert export_file.exists()
        text = export_file.read_text(encoding="utf-8")
        assert "文风DNA" in text


class TestCharacterMapping:
    """测试角色映射方案。"""

    def test_save_character_mapping(self, shenmi_project):
        """应成功保存角色映射。"""
        result = save_analysis.invoke({"key": "character_mapping", "content": CHARACTER_MAPPING})
        assert "保存成功" in result

    def test_mapping_preserves_structure(self, shenmi_project):
        """角色映射应保留表格结构。"""
        save_analysis.invoke({"key": "character_mapping", "content": CHARACTER_MAPPING})
        result = get_analysis.invoke({"key": "character_mapping"})
        assert "罗靖/加隆" in result
        assert "林夕/艾琳" in result
        assert "里昂" in result
        assert "银枫学院" in result

    def test_power_system_mapping(self, shenmi_project):
        """金手指映射应体现情绪炼金机制。"""
        save_analysis.invoke({"key": "character_mapping", "content": CHARACTER_MAPPING})
        result = get_analysis.invoke({"key": "character_mapping"})
        assert "情绪炼金" in result
        assert "晶体" in result
        assert "雾气" in result


class TestPowerSystem:
    """测试金手指改编方案。"""

    def test_save_power_system(self, shenmi_project):
        """应成功保存金手指设计。"""
        result = save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        assert "保存成功" in result

    def test_power_system_dna_correspondence(self, shenmi_project):
        """金手指应包含情绪来源→晶体颜色→能力效果的对应关系。"""
        save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        result = get_analysis.invoke({"key": "power_system"})
        # 五种情绪来源
        assert "怒" in result
        assert "哀" in result
        assert "喜" in result
        assert "爱" in result
        assert "欲" in result
        # 对应的能力效果
        assert "爆发力" in result
        assert "感知增强" in result
        assert "治愈" in result
        assert "意志力" in result

    def test_power_system_crystal_types(self, shenmi_project):
        """应包含五种情绪晶体颜色。"""
        save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        result = get_analysis.invoke({"key": "power_system"})
        assert "暗金色" in result  # 爱
        assert "赤红色" in result  # 怒
        assert "墨黑色" in result  # 哀
        assert "金色" in result  # 喜
        assert "深紫色" in result  # 欲

    def test_power_system_harvest_conditions(self, shenmi_project):
        """应包含严格的采集条件。"""
        save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        result = get_analysis.invoke({"key": "power_system"})
        assert "波动" in result
        assert "强烈" in result
        assert "接触" in result

    def test_power_system_quality_grades(self, shenmi_project):
        """应包含晶体品质分级。"""
        save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        result = get_analysis.invoke({"key": "power_system"})
        assert "浑浊" in result
        assert "通透" in result
        assert "完美" in result

    def test_power_system_negative_effects(self, shenmi_project):
        """应包含被采集者的负面影响。"""
        save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        result = get_analysis.invoke({"key": "power_system"})
        assert "情绪变淡" in result
        assert "情感空白" in result
        assert "情感麻木" in result


class TestSaveAnalysis:
    """测试通用 key-value 分析保存（save_analysis 是通用存储）。"""

    def test_save_adaptation_plan(self, shenmi_project):
        """应成功保存改编计划（通用 key-value）。"""
        result = save_analysis.invoke({"key": "adaptation_plan", "content": ADAPTATION_PLAN})
        assert "保存成功" in result

    def test_plan_has_two_chapters(self, shenmi_project):
        """改编计划应包含两章。"""
        save_analysis.invoke({"key": "adaptation_plan", "content": ADAPTATION_PLAN})
        result = get_analysis.invoke({"key": "adaptation_plan"})
        plan = json.loads(result)
        assert len(plan) == 2
        assert plan[0]["chapter"] == 1
        assert plan[1]["chapter"] == 2

    def test_plan_scene_mapping(self, shenmi_project):
        """每章应有场景映射。"""
        save_analysis.invoke({"key": "adaptation_plan", "content": ADAPTATION_PLAN})
        result = get_analysis.invoke({"key": "adaptation_plan"})
        plan = json.loads(result)
        for ch in plan:
            assert "scene_mapping" in ch
            assert len(ch["scene_mapping"]) >= 3


# ===========================================================================
# 第三部分：仿写章节生成与保存
# ===========================================================================
class TestChapter1Generation:
    """测试第1章仿写生成。"""

    def test_save_chapter1(self, shenmi_project):
        """应成功保存仿写第1章。"""
        result = save_chapter.invoke(
            {
                "chapter": 1,
                "content": CHAPTER_1_CONTENT,
                "summary": CHAPTER_1_SUMMARY,
                "title": "觉醒",
            }
        )
        assert "保存成功" in result
        assert "1" in result

    def test_chapter1_file_on_disk(self, shenmi_project):
        """第1章应写入磁盘文件。"""
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": CHAPTER_1_CONTENT,
                "summary": CHAPTER_1_SUMMARY,
                "title": "觉醒",
            }
        )
        chapter_file = shenmi_project / "chapters" / "chapter-001.md"
        assert chapter_file.exists()
        text = chapter_file.read_text(encoding="utf-8")
        assert "第1章 觉醒" in text
        assert "林夕" in text
        assert "艾琳" in text

    def test_chapter1_preserves_style_dna(self, shenmi_project):
        """仿写第1章应保留原作文风DNA。"""
        # 短句+拟声词开篇（原作：轰隆→嘭，仿写：嗞啦→啪）
        assert "嗞啦" in CHAPTER_1_CONTENT
        assert "啪" in CHAPTER_1_CONTENT
        # 穿越意识流（"我死了？"对应"我死了么？"）
        assert "我死了" in CHAPTER_1_CONTENT
        # 记忆融合
        assert "记忆" in CHAPTER_1_CONTENT
        assert "艾琳" in CHAPTER_1_CONTENT

    def test_chapter1_character_substitution(self, shenmi_project):
        """第1章角色替换正确。"""
        # 原作角色不应出现
        assert "加隆" not in CHAPTER_1_CONTENT
        assert "罗靖" not in CHAPTER_1_CONTENT
        assert "隆巴尔" not in CHAPTER_1_CONTENT
        # 仿写角色应出现
        assert "林夕" in CHAPTER_1_CONTENT
        assert "艾琳" in CHAPTER_1_CONTENT
        assert "梅瑟尔" in CHAPTER_1_CONTENT
        assert "里昂" in CHAPTER_1_CONTENT

    def test_chapter1_world_setting_adapted(self, shenmi_project):
        """第1章世界观改编正确。"""
        # 保留的世界观元素
        assert "亚路联邦" in CHAPTER_1_CONTENT
        assert "威斯曼帝国" in CHAPTER_1_CONTENT
        # 改编的元素
        assert "银枫" in CHAPTER_1_CONTENT  # 圣莺→银枫
        assert "制药" in CHAPTER_1_CONTENT  # 橡胶→制药

    def test_chapter1_word_count_matches_source(self, shenmi_project):
        """仿写字数应与原作章节相近（3500-4500字）。"""
        char_count = len(CHAPTER_1_CONTENT)
        assert 3000 < char_count < 5000, f"第1章字数{char_count}，应在3000-5000之间"


class TestChapter2Generation:
    """测试第2章仿写生成。"""

    def test_save_chapter2(self, shenmi_project):
        """应成功保存仿写第2章。"""
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": CHAPTER_1_CONTENT,
                "summary": CHAPTER_1_SUMMARY,
                "title": "觉醒",
            }
        )
        result = save_chapter.invoke(
            {
                "chapter": 2,
                "content": CHAPTER_2_CONTENT,
                "summary": CHAPTER_2_SUMMARY,
                "title": "银枫学院",
            }
        )
        assert "保存成功" in result
        assert "2" in result

    def test_chapter2_file_on_disk(self, shenmi_project):
        """第2章应写入磁盘文件。"""
        save_chapter.invoke(
            {
                "chapter": 2,
                "content": CHAPTER_2_CONTENT,
                "summary": CHAPTER_2_SUMMARY,
                "title": "银枫学院",
            }
        )
        chapter_file = shenmi_project / "chapters" / "chapter-002.md"
        assert chapter_file.exists()
        text = chapter_file.read_text(encoding="utf-8")
        assert "银枫学院" in text

    def test_chapter2_power_system_adapted(self, shenmi_project):
        """第2章金手指应为情绪炼金（非属性面板）。"""
        # 原作金手指不应出现
        assert "力量0.31" not in CHAPTER_2_CONTENT
        assert "敏捷0.22" not in CHAPTER_2_CONTENT
        # 情绪炼金核心元素应出现
        assert "暗金色" in CHAPTER_2_CONTENT
        assert "雾气" in CHAPTER_2_CONTENT
        assert "晶体" in CHAPTER_2_CONTENT

    def test_chapter2_preserves_golden_finger_reveal_rhythm(self, shenmi_project):
        """金手指揭示节奏：看到雾气→触碰凝晶→体验暖流→注意到弟弟变化→自我怀疑。"""
        content = CHAPTER_2_CONTENT
        # 1. 先看到雾气
        discover_pos = content.find("暗金色雾气")
        # 2. 触碰凝出晶体
        harvest_pos = content.find("暗金色小晶体")
        # 3. 体验暖流
        warmth_pos = content.find("暖流")
        # 4. 注意到弟弟变化
        change_pos = (
            content.find("语气变冷") if content.find("语气变冷") > 0 else content.find("冷了一点点")
        )
        # 5. 自我怀疑
        doubt_pos = content.find("和刚才有关")
        assert discover_pos > 0 and harvest_pos > 0 and warmth_pos > 0
        assert change_pos > 0 and doubt_pos > 0
        assert discover_pos < harvest_pos < warmth_pos < change_pos < doubt_pos, (
            "金手指揭示节奏应为：看到雾气→凝晶→暖流→弟弟变化→怀疑"
        )

    def test_chapter2_no_numerical_stats(self, shenmi_project):
        """第2章不应包含数值型属性（如0.28、0.35等小数点数值模式）。"""
        # 正则匹配类似 "0.28" "0.31" 的数值模式
        matches = re.findall(r"\d+\.\d+", CHAPTER_2_CONTENT)
        assert len(matches) == 0, f"第2章不应包含数值属性，但找到了: {matches}"

    def test_chapter2_harvest_side_effect_foreshadow(self, shenmi_project):
        """第2章应包含采集后里昂态度变冷的伏笔描写。"""
        content = CHAPTER_2_CONTENT
        # 里昂态度变化的关键描写
        assert "冷了一点" in content or "语气变冷" in content or "冷了一截" in content
        # 具体表现：不再主动提醒/看都没看
        assert "看都没看" in content or "没有像往常" in content

    def test_chapter2_gender_swap_school_scene(self, shenmi_project):
        """校车场景应性别对调：优秀男生→优秀女生。"""
        assert "两个容貌出众的女生" in CHAPTER_2_CONTENT
        assert "男生的目光" in CHAPTER_2_CONTENT

    def test_chapter2_word_count_matches_source(self, shenmi_project):
        """仿写字数应与原作章节相近（原作第2章3611字，允许±30%浮动）。"""
        char_count = len(CHAPTER_2_CONTENT)
        assert 2500 < char_count < 5000, f"第2章字数{char_count}，应在2500-5000之间"


# ===========================================================================
# 第四部分：生成上下文完整性验证
# ===========================================================================
@pytest.mark.timeout(INDEX_TIMEOUT)
class TestGenerationContext:
    """测试生成上下文功能（需要完整仿写环境）。"""

    def test_context_ch1_includes_source_text(self, shenmi_project):
        """第1章上下文应包含源小说原文。"""
        index_source.invoke({})
        save_analysis.invoke({"key": "character_mapping", "content": CHARACTER_MAPPING})
        ctx = get_generation_context.invoke({"chapter": 1})
        assert "罗靖" in ctx  # 源小说原文
        assert "风格参考" in ctx or "源小说" in ctx

    def test_context_ch1_includes_analysis(self, shenmi_project):
        """第1章上下文应包含角色映射。"""
        index_source.invoke({})
        save_analysis.invoke({"key": "character_mapping", "content": CHARACTER_MAPPING})
        ctx = get_generation_context.invoke({"chapter": 1})
        assert "林夕/艾琳" in ctx

    def test_context_ch2_includes_ch1_summary(self, shenmi_project):
        """第2章上下文应包含第1章摘要。"""
        index_source.invoke({})
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": CHAPTER_1_CONTENT,
                "summary": CHAPTER_1_SUMMARY,
                "title": "觉醒",
            }
        )
        ctx = get_generation_context.invoke({"chapter": 2})
        assert "林夕" in ctx
        assert "银枫" in ctx or "艾琳" in ctx

    def test_context_ch2_includes_reference_hints(self, shenmi_project):
        """第2章上下文应包含按需查阅提示。"""
        index_source.invoke({})
        ctx = get_generation_context.invoke({"chapter": 2})
        assert "按需查阅" in ctx
        assert "world_setting" in ctx

    def test_context_ch2_includes_power_reference(self, shenmi_project):
        """第2章上下文应包含金手指查阅提示。"""
        index_source.invoke({})
        ctx = get_generation_context.invoke({"chapter": 2})
        assert "power_system" in ctx


# ===========================================================================
# 第五部分：完整工作流端到端测试
# ===========================================================================
@pytest.mark.timeout(INDEX_TIMEOUT)
class TestFullImitationWorkflow:
    """端到端测试：从索引到生成两章的完整流程。"""

    def test_full_workflow(self, shenmi_project):
        """完整仿写工作流：索引→分析→保存方案→生成两章→验证状态。"""
        # Step 1: 索引源小说
        idx_result = index_source.invoke({})
        assert "索引完成" in idx_result
        assert "1372" in idx_result or "章" in idx_result

        # Step 2: 验证能读取前两章
        ch1 = read_source_chapter.invoke({"chapter": 1})
        assert "罗靖" in ch1
        ch2 = read_source_chapter.invoke({"chapter": 2})
        assert "加隆" in ch2

        # Step 3: 保存方案推荐（4个方案供用户选择）
        save_analysis.invoke({"key": "adaptation_proposals", "content": ADAPTATION_PROPOSALS})

        # Step 4: 用户选择S+方案后，保存具体分析
        save_analysis.invoke({"key": "dna_analysis", "content": DNA_ANALYSIS})
        save_analysis.invoke({"key": "character_mapping", "content": CHARACTER_MAPPING})
        save_analysis.invoke({"key": "power_system", "content": POWER_SYSTEM})
        save_analysis.invoke({"key": "world_setting", "content": WORLD_SETTING})

        # Step 5: 验证生成上下文
        ctx1 = get_generation_context.invoke({"chapter": 1})
        assert "源小说" in ctx1 or "风格参考" in ctx1
        assert "林夕/艾琳" in ctx1  # 角色映射

        # Step 6: 保存仿写章节
        save_chapter.invoke(
            {
                "chapter": 1,
                "content": CHAPTER_1_CONTENT,
                "summary": CHAPTER_1_SUMMARY,
                "title": "觉醒",
            }
        )
        save_chapter.invoke(
            {
                "chapter": 2,
                "content": CHAPTER_2_CONTENT,
                "summary": CHAPTER_2_SUMMARY,
                "title": "银枫学院",
            }
        )

        # Step 7: 第2章上下文应包含第1章摘要
        ctx2 = get_generation_context.invoke({"chapter": 2})
        assert "林夕" in ctx2

        # Step 8: 验证项目状态
        status = get_project_status.invoke({})
        assert "2 章" in status or "2章" in status
        assert "dna_analysis" in status
        assert "character_mapping" in status
        assert "power_system" in status
        assert "world_setting" in status
        assert "adaptation_proposals" in status

        # Step 9: 验证磁盘文件
        assert (shenmi_project / "chapters" / "chapter-001.md").exists()
        assert (shenmi_project / "chapters" / "chapter-002.md").exists()
        assert (shenmi_project / "analysis" / "dna_analysis.md").exists()
        assert (shenmi_project / "analysis" / "character_mapping.md").exists()
        assert (shenmi_project / "analysis" / "power_system.md").exists()
        assert (shenmi_project / "analysis" / "world_setting.md").exists()
        assert (shenmi_project / "analysis" / "adaptation_proposals.md").exists()


# ===========================================================================
# 第六部分：写作经验库（SkillRL 经验蒸馏）
# ===========================================================================
class TestSkillLibrary:
    """测试用户反馈技能库功能。"""

    def test_record_success_pattern(self, shenmi_project):
        """应成功记录成功模式。"""
        result = record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "success_pattern",
                "category": "writing",
                "content": "五感交织描写效果好，读者反馈沉浸感强",
            }
        )
        assert "写作经验已记录" in result
        assert "成功模式" in result

    def test_record_lesson_learned(self, shenmi_project):
        """应成功记录经验教训。"""
        result = record_writing_skill.invoke(
            {
                "chapter": 2,
                "skill_type": "lesson_learned",
                "category": "pacing",
                "content": "节奏太快，缺少舒缓过渡段",
            }
        )
        assert "写作经验已记录" in result
        assert "经验教训" in result

    def test_invalid_skill_type(self, shenmi_project):
        """无效的 skill_type 应返回错误。"""
        result = record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "invalid_type",
                "category": "writing",
                "content": "test",
            }
        )
        assert "错误" in result
        assert "skill_type" in result

    def test_invalid_category(self, shenmi_project):
        """无效的 category 应返回错误。"""
        result = record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "success_pattern",
                "category": "invalid_cat",
                "content": "test",
            }
        )
        assert "错误" in result
        assert "category" in result

    def test_content_truncation(self, shenmi_project):
        """超过200字的 content 应被截断。"""
        long_content = "这是一段很长的经验描述" * 30  # ~300 chars
        result = record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "success_pattern",
                "category": "description",
                "content": long_content,
            }
        )
        assert "写作经验已记录" in result
        # Verify truncation in database
        db = _get_db()
        with db._connection() as conn:
            row = conn.execute(
                "SELECT content FROM imitate_skill_library ORDER BY id DESC LIMIT 1"
            ).fetchone()
        assert len(row[0]) <= 200

    def test_build_skill_library_prompt_empty(self, shenmi_project):
        """空表应返回空字符串。"""
        db = _get_db()
        result = _build_skill_library_prompt(db, 1)
        assert result == ""

    def test_build_skill_library_prompt_with_data(self, shenmi_project):
        """有数据时应返回格式化的经验库提示。"""
        record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "success_pattern",
                "category": "writing",
                "content": "五感交织描写效果好",
            }
        )
        record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "lesson_learned",
                "category": "pacing",
                "content": "节奏太快需要舒缓",
            }
        )
        db = _get_db()
        result = _build_skill_library_prompt(db, 2)
        assert "写作经验库" in result
        assert "成功模式" in result
        assert "经验教训" in result
        assert "五感交织" in result
        assert "节奏太快" in result

    def test_skill_library_in_generation_context(self, shenmi_project):
        """技能库数据应出现在 get_generation_context 返回中。"""
        record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "success_pattern",
                "category": "writing",
                "content": "环境映射情绪的写法用户很喜欢",
            }
        )
        ctx = get_generation_context.invoke({"chapter": 2})
        assert "写作经验库" in ctx
        assert "环境映射情绪" in ctx

    def test_record_with_source_feedback(self, shenmi_project):
        """应支持记录用户原始反馈。"""
        result = record_writing_skill.invoke(
            {
                "chapter": 1,
                "skill_type": "success_pattern",
                "category": "character",
                "content": "动作性格化刻画里昂效果很好",
                "source_feedback": "里昂的冷淡表现写得很到位",
            }
        )
        assert "写作经验已记录" in result
        db = _get_db()
        with db._connection() as conn:
            row = conn.execute(
                "SELECT source_feedback FROM imitate_skill_library ORDER BY id DESC LIMIT 1"
            ).fetchone()
        assert "冷淡" in row[0]
