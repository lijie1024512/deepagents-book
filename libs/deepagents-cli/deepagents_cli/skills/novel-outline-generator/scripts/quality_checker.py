#!/usr/bin/env python3
"""
大纲质量检查器

功能：验证大纲质量，检查逻辑一致性、角色合理性、爽点密度、伏笔设置等
"""

import sys
import re
from pathlib import Path
from typing import List, Dict


class QualityChecker:
    """质量检查器"""

    def __init__(self, input_file):
        """
        初始化检查器

        Args:
            input_file: 输入文件路径
        """
        self.input_file = Path(input_file)

        # 读取输入文件
        with open(self.input_file, 'r', encoding='utf-8') as f:
            self.content = f.read()

        # 解析章节
        self.chapters = self._parse_chapters()

    def _parse_chapters(self):
        """解析章节"""
        # 使用正则表达式匹配章节
        chapter_pattern = re.compile(
            r'### 第(\d+)章：《(.+?)》\n\n\*\*章节概述\*\*:(.+?)\n\n\*\*情节点\*\*:(.+?)\n\n\*\*情感变化\*\*:(.+?)\n\n\*\*爽点\*\*:(.+?)\n\n\*\*钩子\*\*:(.+?)\n\n\*\*伏笔\*\*:(.+?)(?=\n\n### 第\d+章|\Z)',
            re.DOTALL
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
                'title': chapter_title,
                'overview': chapter_overview,
                'plot_points': plot_points,
                'emotion_change': emotion_change,
                'highlights': highlights,
                'hooks': hooks,
                'foreshadowings': foreshadowings,
            }

        return chapters

    def check_all(self):
        """执行所有检查"""
        report = {
            'total_chapters': len(self.chapters),
            'checks': [],
            'warnings': [],
            'errors': [],
            'summary': '',
        }

        # 检查1：每个章节是否包含所有必需字段
        self._check_required_fields(report)

        # 检查2：情节点具体化
        self._check_plot_specificity(report)

        # 检查3：角色逻辑性
        self._check_character_logic(report)

        # 检查4：能量发现自然化
        self._check_energy_discovery(report)

        # 检查5：收服势力合理化
        self._check_force_acquisition(report)

        # 检查6：情节点数量
        self._check_plot_point_count(report)

        # 检查7：爽点密度
        self._check_highlight_density(report)

        # 检查8：伏笔设置
        self._check_foreshadowing(report)

        # 生成总结
        self._generate_summary(report)

        return report

    def _check_required_fields(self, report):
        """检查必需字段"""
        check_name = '必需字段检查'
        passed = True
        issues = []

        for chapter_num, chapter_data in self.chapters.items():
            required_fields = [
                'overview', 'plot_points', 'emotion_change',
                'highlights', 'hooks', 'foreshadowings'
            ]

            for field in required_fields:
                if not chapter_data.get(field):
                    passed = False
                    issues.append(f"第{chapter_num}章缺少{field}字段")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['errors'].append(issue)

    def _check_plot_specificity(self, report):
        """检查情节点具体化"""
        check_name = '情节点具体化检查'
        passed = True
        issues = []

        vague_keywords = [
            '获得军功', '获得势力', '获得能力',
            '李寒发现', '李寒利用',
            '编造情报', '提供情报',
            '收服', '接手'
        ]

        for chapter_num, chapter_data in self.chapters.items():
            plot_points = chapter_data['plot_points']

            # 检查是否包含模糊关键词
            for keyword in vague_keywords:
                if keyword in plot_points:
                    # 检查是否有具体描述
                    if len(plot_points) < 100:
                        passed = False
                        issues.append(f"第{chapter_num}章的情节点'{keyword}'描述过于模糊")
                        break

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _check_character_logic(self, report):
        """检查角色逻辑性"""
        check_name = '角色逻辑性检查'
        passed = True
        issues = []

        # 检查老鼠的角色行为
        for chapter_num, chapter_data in self.chapters.items():
            if '老鼠' in chapter_data['plot_points']:
                # 老鼠阴险狡诈，不应该直接行动
                if '直接派人暗杀' in chapter_data['plot_points']:
                    passed = False
                    issues.append(f"第{chapter_num}章：老鼠作为阴险狡诈的角色，不应该直接派人暗杀")

        # 检查蒙卡的角色行为
        for chapter_num, chapter_data in self.chapters.items():
            if '蒙卡' in chapter_data['plot_points']:
                # 蒙卡暴躁残暴，不应该冷静思考
                if '冷静思考' in chapter_data['plot_points']:
                    passed = False
                    issues.append(f"第{chapter_num}章：蒙卡作为暴躁残暴的角色，不应该冷静思考")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _check_energy_discovery(self, report):
        """检查能量发现自然化"""
        check_name = '能量发现自然化检查'
        passed = True
        issues = []

        energy_keywords = ['能量', '系统', '加点']

        for chapter_num, chapter_data in self.chapters.items():
            plot_points = chapter_data['plot_points']

            # 检查是否包含能量相关内容
            if any(keyword in plot_points for keyword in energy_keywords):
                # 检查是否是自然发现
                if '主动查看' in plot_points or '发现系统' in plot_points:
                    # 检查是否有自然的过渡描述
                    if '身体感觉' not in plot_points and '自动弹出' not in plot_points:
                        passed = False
                        issues.append(f"第{chapter_num}章：能量发现过程不够自然，建议改为'身体感觉变化，系统界面自动弹出'")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _check_force_acquisition(self, report):
        """检查收服势力合理化"""
        check_name = '收服势力合理化检查'
        passed = True
        issues = []

        for chapter_num, chapter_data in self.chapters.items():
            plot_points = chapter_data['plot_points']

            # 检查是否包含收服/接手势力
            if '收服' in plot_points or '接手' in plot_points:
                # 检查是否有合理的依据
                if '临时任命' not in plot_points and '主动投靠' not in plot_points:
                    passed = False
                    issues.append(f"第{chapter_num}章：收服势力缺乏合理依据，建议说明'临时任命'或'墙头草主动投靠'")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _check_plot_point_count(self, report):
        """检查情节点数量"""
        check_name = '情节点数量检查'
        passed = True
        issues = []

        for chapter_num, chapter_data in self.chapters.items():
            plot_points = chapter_data['plot_points']

            # 计算情节点数量
            count = len(re.findall(r'\d+\. 【', plot_points))

            if count < 7:
                passed = False
                issues.append(f"第{chapter_num}章的情节点数量过少（{count}个），建议至少7个")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _check_highlight_density(self, report):
        """检查爽点密度"""
        check_name = '爽点密度检查'
        passed = True
        issues = []

        for chapter_num, chapter_data in self.chapters.items():
            highlights = chapter_data['highlights']

            # 检查是否有爽点
            if not highlights or '无' in highlights:
                passed = False
                issues.append(f"第{chapter_num}章没有爽点，建议至少添加1个爽点")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _check_foreshadowing(self, report):
        """检查伏笔设置"""
        check_name = '伏笔设置检查'
        passed = True
        issues = []

        for chapter_num, chapter_data in self.chapters.items():
            foreshadowings = chapter_data['foreshadowings']

            # 检查是否有伏笔
            if not foreshadowings or '无' in foreshadowings:
                passed = False
                issues.append(f"第{chapter_num}章没有伏笔，建议至少设置1个伏笔")

        report['checks'].append({
            'name': check_name,
            'passed': passed,
            'issues': issues
        })

        if not passed:
            for issue in issues:
                report['warnings'].append(issue)

    def _generate_summary(self, report):
        """生成总结"""
        total_checks = len(report['checks'])
        passed_checks = sum(1 for check in report['checks'] if check['passed'])

        if passed_checks == total_checks:
            report['summary'] = f"✅ 所有检查通过！共{total_checks}项检查全部通过。"
        elif passed_checks >= total_checks * 0.8:
            report['summary'] = f"⚠️ 大部分检查通过（{passed_checks}/{total_checks}），但存在一些问题需要注意。"
        else:
            report['summary'] = f"❌ 多项检查失败（{passed_checks}/{total_checks}），建议重新优化大纲。"

    def generate_report(self, output_file=None):
        """生成检查报告"""
        report = self.check_all()

        # 生成报告文本
        report_text = f"""# 大纲质量检查报告

## 检查总结
{report['summary']}

## 检查详情

### 总体情况
- 总章节数：{report['total_chapters']}
- 检查项目：{len(report['checks'])}
- 通过项目：{sum(1 for check in report['checks'] if check['passed'])}
- 警告数量：{len(report['warnings'])}
- 错误数量：{len(report['errors'])}

### 检查项目

"""

        for check in report['checks']:
            status = "✅ 通过" if check['passed'] else "❌ 不通过"
            report_text += f"\n#### {check['name']}\n"
            report_text += f"**状态**: {status}\n"

            if check['issues']:
                report_text += "**问题**:\n"
                for issue in check['issues']:
                    report_text += f"- {issue}\n"

        if report['warnings']:
            report_text += "\n### 警告\n\n"
            for warning in report['warnings']:
                report_text += f"- ⚠️ {warning}\n"

        if report['errors']:
            report_text += "\n### 错误\n\n"
            for error in report['errors']:
                report_text += f"- ❌ {error}\n"

        # 写入文件
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)

        return report_text


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='大纲质量检查器')
    parser.add_argument('--input', required=True, help='输入文件路径')
    parser.add_argument('--report', help='报告文件路径')

    args = parser.parse_args()

    checker = QualityChecker(input_file=args.input)
    report = checker.generate_report(output_file=args.report)

    print(report)


if __name__ == '__main__':
    main()
