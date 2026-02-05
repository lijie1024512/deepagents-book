#!/bin/bash
# 解压 deepagents-book.zip 并覆盖当前项目
#
# 使用方法：
#   bash unzip_update.sh

ZIP_FILE="e:/git/deepagents-book/deepagents-book.zip"
TARGET_DIR="e:/git/deepagents-book"

# 检查 zip 文件是否存在
if [ ! -f "$ZIP_FILE" ]; then
    echo "错误: zip 文件不存在: $ZIP_FILE"
    exit 1
fi

echo "开始解压 $ZIP_FILE ..."

# 解压到目标目录
unzip -o "$ZIP_FILE" -d "$TARGET_DIR"

if [ $? -ne 0 ]; then
    echo "解压失败！"
    exit 1
fi

# 处理嵌套文件夹：如果存在 deepagents-book/deepagents-book，则移动内容到根目录
NESTED_DIR="$TARGET_DIR/deepagents-book"
if [ -d "$NESTED_DIR" ]; then
    echo "检测到嵌套文件夹，正在移动文件..."
    cp -rf "$NESTED_DIR"/* "$TARGET_DIR/"
    rm -rf "$NESTED_DIR"
    echo "嵌套文件夹已处理"
fi

echo "解压完成！"
