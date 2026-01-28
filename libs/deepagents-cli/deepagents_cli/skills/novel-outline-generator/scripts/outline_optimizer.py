#!/usr/bin/env python3
"""
小说大纲优化器

功能：根据情节逻辑指南，优化现有大纲的指定章节
重点：情节具体化、角色逻辑化、能量发现自然化、收服势力合理化等
"""

import sys
import re
from pathlib import Path


class OutlineOptimizer:
    """大纲优化器"""

    def __init__(self, input_file, output_file, chapter_range=None):
        """
        初始化优化器

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            chapter_range: 章节范围，如 "5-7" 表示第5-7章
        """
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.chapter_range = chapter_range

        # 读取输入文件
        with open(self.input_file, 'r', encoding='utf-8') as f:
            self.content = f.read()

        # 解析章节
        self.chapters = self._parse_chapters()

    def _parse_chapters(self):
        """解析章节"""
        # 使用正则表达式匹配章节
        chapter_pattern = re.compile(
            r'### 第(\d+)章：《(.+?)》\n\n\*\*章节概述\*\*:(.+?)\n\n\*\*情节点\*\*:(.+?)(?=\n\n\*\*情感变化\*\*:|\Z)',
            re.DOTALL
        )

        chapters = {}
        for match in chapter_pattern.finditer(self.content):
            chapter_num = int(match.group(1))
            chapter_title = match.group(2)
            chapter_overview = match.group(3).strip()
            plot_points = match.group(4).strip()

            chapters[chapter_num] = {
                'title': chapter_title,
                'overview': chapter_overview,
                'plot_points': plot_points,
            }

        return chapters

    def optimize_chapter(self, chapter_num, chapter_data):
        """
        优化单个章节

        Args:
            chapter_num: 章节号
            chapter_data: 章节数据

        Returns:
            优化后的章节数据
        """
        optimized = chapter_data.copy()

        # 优化情节点
        optimized['plot_points'] = self._optimize_plot_points(
            chapter_num, chapter_data['plot_points']
        )

        # 优化章节概述
        optimized['overview'] = self._optimize_overview(
            chapter_num, chapter_data['overview']
        )

        return optimized

    def _optimize_plot_points(self, chapter_num, plot_points):
        """
        优化情节点

        Args:
            chapter_num: 章节号
            plot_points: 情节点文本

        Returns:
            优化后的情节点文本
        """
        # 分割情节点
        point_pattern = re.compile(r'\d+\. 【(.+?)】(.+)')
        points = []
        for match in point_pattern.finditer(plot_points):
            point_title = match.group(1)
            point_content = match.group(2).strip()
            points.append({
                'title': point_title,
                'content': point_content
            })

        # 优化每个情节点
        optimized_points = []
        for point in points:
            optimized = self._optimize_single_point(chapter_num, point)
            optimized_points.append(optimized)

        # 重新组合
        result = []
        for i, point in enumerate(optimized_points, 1):
            result.append(f"{i}. 【{point['title']}】{point['content']}")

        return '\n'.join(result)

    def _optimize_single_point(self, chapter_num, point):
        """
        优化单个情节点

        Args:
            chapter_num: 章节号
            point: 情节点数据

        Returns:
            优化后的情节点
        """
        optimized = point.copy()

        # 优化策略

        # 策略1：情节点具体化
        if self._is_vague(point['content']):
            optimized['content'] = self._make_specific(point['content'], chapter_num)

        # 策略2：补充细节
        if self._is_lack_detail(point['content']):
            optimized['content'] = self._add_detail(point['content'], chapter_num)

        return optimized

    def _is_vague(self, content):
        """判断是否模糊"""
        vague_keywords = [
            '获得军功', '获得势力', '获得能力',
            '李寒发现', '李寒利用',
            '编造情报', '提供情报',
            '收服', '接手'
        ]

        for keyword in vague_keywords:
            if keyword in content:
                return True

        return False

    def _make_specific(self, content, chapter_num):
        """让内容具体化"""
        # 根据章节号和内容，生成更具体的描述
        # 这里是示例，实际应该根据上下文生成

        if '获得军功' in content:
            # 生成更具体的军功获得描述
            return content.replace('获得军功',
                '蒙卡对李寒刮目相看："没想到你小子还有这本事。这次记你一等功！"'
            )

        if '获得势力' in content:
            # 生成更具体的势力获得描述
            return content.replace('获得势力',
                '李寒主动向准将请示，组织临时海军部队维持秩序。准将看到李寒能力出众，临时任命李寒负责谢尔兹镇的海军事务。李寒利用这个机会，收服了一些老鼠和蒙卡的手下（这些人都是墙头草，看到李寒已经是一等兵，主动投靠）'
            )

        if '李寒发现' in content and '能量' in content:
            # 生成更自然的能量发现描述
            return content.replace('李寒发现',
                '李寒感觉身体有种奇怪的变化，系统界面自动弹出，他恍然大悟——原来军衔晋升能增加能量！这是自然的过渡，不是他提前知道的'
            )

        return content

    def _is_lack_detail(self, content):
        """判断是否缺乏细节"""
        # 检查是否包含人物、动作、结果
        has_person = any(word in content for word in ['李寒', '老鼠', '蒙卡', '索隆', '山治'])
        has_action = any(word in content for word in ['说', '做', '看', '想', '派', '去', '杀'])
        has_result = '，' in content or '。' in content

        return not (has_person and has_action and has_result)

    def _add_detail(self, content, chapter_num):
        """补充细节"""
        # 这里是示例，实际应该根据上下文补充
        return content

    def _optimize_overview(self, chapter_num, overview):
        """
        优化章节概述

        Args:
            chapter_num: 章节号
            overview: 章节概述

        Returns:
            优化后的章节概述
        """
        # 章节概述优化策略
        # 这里是示例，实际应该根据上下文优化
        return overview

    def optimize(self):
        """执行优化"""
        # 确定要优化的章节范围
        if self.chapter_range:
            start, end = map(int, self.chapter_range.split('-'))
            target_chapters = list(range(start, end + 1))
        else:
            target_chapters = list(self.chapters.keys())

        # 优化每个章节
        for chapter_num in target_chapters:
            if chapter_num in self.chapters:
                self.chapters[chapter_num] = self.optimize_chapter(
                    chapter_num, self.chapters[chapter_num]
                )

        # 生成输出
        self._generate_output()

    def _generate_output(self):
        """生成输出文件"""
        # 替换优化后的章节内容
        output_content = self.content

        for chapter_num, chapter_data in self.chapters.items():
            if chapter_num in range(
                int(self.chapter_range.split('-')[0]),
                int(self.chapter_range.split('-')[1]) + 1
            ) if self.chapter_range else range(1, len(self.chapters) + 1):
                # 查找并替换章节内容
                chapter_pattern = re.compile(
                    rf'(### 第{chapter_num}章：《.+?》\n\n\*\*章节概述\*\*:.+?\n\n\*\*情节点\*\*:)(.+?)(?=\n\n\*\*情感变化\*\*:)',
                    re.DOTALL
                )

                new_plot = f"【情节点】\n{chapter_data['plot_points']}"

                output_content = chapter_pattern.sub(
                    rf'\1{chapter_data["plot_points"]}',
                    output_content
                )

        # 写入输出文件
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(output_content)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='小说大纲优化器')
    parser.add_argument('--input', required=True, help='输入文件路径')
    parser.add_argument('--output', required=True, help='输出文件路径')
    parser.add_argument('--chapters', help='章节范围，如 5-7')

    args = parser.parse_args()

    optimizer = OutlineOptimizer(
        input_file=args.input,
        output_file=args.output,
        chapter_range=args.chapters
    )

    optimizer.optimize()

    print(f"优化完成，输出文件：{args.output}")


if __name__ == '__main__':
    main()
