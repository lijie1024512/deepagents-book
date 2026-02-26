#!/usr/bin/env python3
"""
正文质量检查器

用于检查小说正文的质量问题，包括：
- 流水账检测
- OOC检测
- 节奏检测
- 描写质量检测

使用方法：
    python text_quality_checker.py --input chapter.md
    python text_quality_checker.py --input chapter.md --output report.md
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class QualityIssue:
    """质量问题"""

    issue_type: str  # 问题类型
    severity: str  # 严重程度: warning, error
    location: str  # 位置描述
    description: str  # 问题描述
    suggestion: str  # 修改建议


@dataclass
class QualityReport:
    """质量报告"""

    file_path: str
    total_chars: int
    total_paragraphs: int
    issues: list[QualityIssue]
    score: int  # 0-100分


def detect_waterfall_writing(text: str) -> list[QualityIssue]:
    """检测流水账问题"""
    issues = []

    # 分割成段落
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    for i, para in enumerate(paragraphs):
        # 分割成句子
        sentences = re.split(r"[。！？]", para)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 检测连续纯叙述
        consecutive_narrative = 0
        for sent in sentences:
            # 简单判断：如果句子没有感官词汇、没有情感词汇，视为纯叙述
            sensory_words = [
                "看",
                "听",
                "闻",
                "尝",
                "触",
                "感觉",
                "冷",
                "热",
                "痛",
                "响",
                "味",
                "光",
                "暗",
            ]
            emotion_words = [
                "心",
                "想",
                "觉得",
                "感到",
                "害怕",
                "兴奋",
                "紧张",
                "愤怒",
                "期待",
                "担忧",
            ]
            dialogue_pattern = r'["「『].*?["」』]'

            has_sensory = any(word in sent for word in sensory_words)
            has_emotion = any(word in sent for word in emotion_words)
            has_dialogue = bool(re.search(dialogue_pattern, sent))

            if not has_sensory and not has_emotion and not has_dialogue:
                consecutive_narrative += 1
            else:
                consecutive_narrative = 0

            if consecutive_narrative >= 3:
                issues.append(
                    QualityIssue(
                        issue_type="流水账",
                        severity="warning",
                        location=f"第{i + 1}段",
                        description="连续3句以上纯叙述，缺少感官描写或情感描写",
                        suggestion="在叙述中穿插感官细节（视觉、听觉、触觉等）或角色的情感反应",
                    )
                )
                break

        # 检测是否完全没有感官描写
        para_has_sensory = any(word in para for word in sensory_words)
        if not para_has_sensory and len(para) > 100:
            issues.append(
                QualityIssue(
                    issue_type="感官缺失",
                    severity="warning",
                    location=f"第{i + 1}段",
                    description="整段没有任何感官描写",
                    suggestion="添加至少2种感官描写（视觉、听觉、触觉、嗅觉、味觉）",
                )
            )

    return issues


def detect_dialogue_issues(text: str) -> list[QualityIssue]:
    """检测对话问题"""
    issues = []

    # 匹配对话
    dialogue_pattern = r'["「『]([^"」』]*?)["」』]'
    dialogues = re.findall(dialogue_pattern, text)

    # 检测连续对话（没有动作/神态描写）
    lines = text.split("\n")
    consecutive_dialogues = 0

    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            consecutive_dialogues = 0
            continue

        has_dialogue = bool(re.search(dialogue_pattern, stripped_line))
        # 简单判断是否有动作描写
        action_words = [
            "说",
            "道",
            "喊",
            "叫",
            "笑",
            "皱眉",
            "点头",
            "摇头",
            "看",
            "站",
            "坐",
            "走",
            "转身",
            "伸手",
            "握",
            "抬",
            "低",
        ]
        has_action = any(word in stripped_line for word in action_words)

        if has_dialogue:
            if not has_action:
                consecutive_dialogues += 1
            else:
                consecutive_dialogues = 0

            if consecutive_dialogues >= 3:
                issues.append(
                    QualityIssue(
                        issue_type="对话呆板",
                        severity="warning",
                        location=f"第{i + 1}行附近",
                        description="连续多句对话没有动作/神态描写",
                        suggestion="为对话添加说话者的动作、表情、语气描写",
                    )
                )
                consecutive_dialogues = 0

    return issues


def detect_pacing_issues(text: str) -> list[QualityIssue]:
    """检测节奏问题"""
    issues = []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # 检测过长段落（可能节奏太慢）
    for i, para in enumerate(paragraphs):
        if len(para) > 800:
            issues.append(
                QualityIssue(
                    issue_type="节奏过慢",
                    severity="warning",
                    location=f"第{i + 1}段",
                    description=f"段落过长（{len(para)}字），可能节奏拖沓",
                    suggestion="考虑拆分段落，或删减不必要的描写",
                )
            )

    # 检测连续短段落（可能节奏太快）
    consecutive_short = 0
    for i, para in enumerate(paragraphs):
        if len(para) < 50:
            consecutive_short += 1
        else:
            consecutive_short = 0

        if consecutive_short >= 5:
            issues.append(
                QualityIssue(
                    issue_type="节奏过快",
                    severity="warning",
                    location=f"第{i + 1}段附近",
                    description="连续多个过短段落，可能信息过载",
                    suggestion="在快节奏段落之间加入适当的描写和过渡",
                )
            )
            consecutive_short = 0

    return issues


def detect_description_quality(text: str) -> list[QualityIssue]:
    """检测描写质量"""
    issues = []

    # 检测是否使用了多种感官
    visual_words = ["看", "见", "光", "暗", "红", "白", "黑", "亮", "闪"]
    audio_words = ["听", "声", "响", "喊", "叫", "吼", "静"]
    tactile_words = ["触", "碰", "冷", "热", "痛", "硬", "软", "滑"]
    olfactory_words = ["闻", "味", "臭", "香", "腥"]
    gustatory_words = ["尝", "甜", "苦", "辣", "咸", "酸"]

    has_visual = any(word in text for word in visual_words)
    has_audio = any(word in text for word in audio_words)
    has_tactile = any(word in text for word in tactile_words)
    has_olfactory = any(word in text for word in olfactory_words)
    has_gustatory = any(word in text for word in gustatory_words)

    sensory_count = sum([has_visual, has_audio, has_tactile, has_olfactory, has_gustatory])

    if sensory_count < 2:
        issues.append(
            QualityIssue(
                issue_type="感官单一",
                severity="warning",
                location="全文",
                description=f"只使用了{sensory_count}种感官描写",
                suggestion="建议至少使用2-3种感官描写（视觉、听觉、触觉、嗅觉、味觉）",
            )
        )

    return issues


def calculate_score(issues: list[QualityIssue]) -> int:
    """计算质量分数"""
    base_score = 100

    for issue in issues:
        if issue.severity == "error":
            base_score -= 15
        elif issue.severity == "warning":
            base_score -= 5

    return max(0, min(100, base_score))


def check_quality(text: str, file_path: str = "未知文件") -> QualityReport:
    """执行完整的质量检查"""
    issues = []

    # 执行各项检查
    issues.extend(detect_waterfall_writing(text))
    issues.extend(detect_dialogue_issues(text))
    issues.extend(detect_pacing_issues(text))
    issues.extend(detect_description_quality(text))

    # 计算分数
    score = calculate_score(issues)

    # 统计基本信息
    total_chars = len(text)
    total_paragraphs = len([p for p in text.split("\n\n") if p.strip()])

    return QualityReport(
        file_path=file_path,
        total_chars=total_chars,
        total_paragraphs=total_paragraphs,
        issues=issues,
        score=score,
    )


def format_report(report: QualityReport) -> str:
    """格式化质量报告"""
    lines = []

    lines.append("# 正文质量检查报告")
    lines.append("")
    lines.append("## 基本信息")
    lines.append(f"- 文件：{report.file_path}")
    lines.append(f"- 总字数：{report.total_chars}")
    lines.append(f"- 总段落数：{report.total_paragraphs}")
    lines.append(f"- 质量评分：{report.score}/100")
    lines.append("")

    if report.issues:
        lines.append("## 发现的问题")
        lines.append("")

        # 按类型分组
        issues_by_type: dict[str, list[QualityIssue]] = {}
        for issue in report.issues:
            if issue.issue_type not in issues_by_type:
                issues_by_type[issue.issue_type] = []
            issues_by_type[issue.issue_type].append(issue)

        for issue_type, issues in issues_by_type.items():
            lines.append(f"### {issue_type} ({len(issues)}处)")
            lines.append("")
            for i, issue in enumerate(issues, 1):
                severity_icon = "⚠️" if issue.severity == "warning" else "❌"
                lines.append(f"{i}. {severity_icon} **{issue.location}**")
                lines.append(f"   - 问题：{issue.description}")
                lines.append(f"   - 建议：{issue.suggestion}")
                lines.append("")

    else:
        lines.append("## 检查结果")
        lines.append("")
        lines.append("✅ 未发现明显的质量问题")

    lines.append("")
    lines.append("---")
    lines.append("*此报告由正文质量检查器自动生成*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="小说正文质量检查器")
    parser.add_argument("--input", "-i", required=True, help="输入文件路径")
    parser.add_argument("--output", "-o", help="输出报告路径（可选）")

    args = parser.parse_args()

    # 读取文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误：文件不存在 - {args.input}")
        return

    text = input_path.read_text(encoding="utf-8")

    # 执行检查
    report = check_quality(text, args.input)

    # 格式化报告
    report_text = format_report(report)

    # 输出
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report_text, encoding="utf-8")
        print(f"报告已保存至：{args.output}")
    else:
        print(report_text)

    # 返回状态码
    return 0 if report.score >= 60 else 1


if __name__ == "__main__":
    exit(main() or 0)
