#!/bin/bash
# 打包 deepagents-cli 项目为 zip 文件
# 用法: ./scripts/pack.sh [output_name]

set -e

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="deepagents-cli"

# 输出文件名（默认带时间戳）
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_NAME="${1:-${PROJECT_NAME}_${TIMESTAMP}}"
OUTPUT_FILE="${PROJECT_DIR}/${OUTPUT_NAME}.zip"

echo "📦 打包项目: $PROJECT_NAME"
echo "   源目录: $PROJECT_DIR"
echo "   输出文件: $OUTPUT_FILE"
echo ""

# 切换到项目目录
cd "$PROJECT_DIR"

# 创建临时排除文件列表
EXCLUDE_FILE=$(mktemp)
cat > "$EXCLUDE_FILE" << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
*.egg
.eggs/
dist/
build/
*.whl

# 虚拟环境
.venv/
venv/
ENV/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Git
.git/
.gitignore

# 测试/缓存
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/
.mypy_cache/
.ruff_cache/

# 系统文件
.DS_Store
Thumbs.db

# 日志
*.log

# 本地配置
.env
.env.local
*.local

# 打包输出
*.zip
EOF

# 执行打包
echo "🔍 排除以下模式:"
cat "$EXCLUDE_FILE" | grep -v '^#' | grep -v '^$' | sed 's/^/   - /'
echo ""

# 使用 zip 打包，排除不需要的文件
zip -r "$OUTPUT_FILE" . \
    -x "*.git/*" \
    -x "*__pycache__/*" \
    -x "*.pyc" \
    -x "*.pyo" \
    -x "*.egg-info/*" \
    -x "*.venv/*" \
    -x "*venv/*" \
    -x "*.pytest_cache/*" \
    -x "*.mypy_cache/*" \
    -x "*.ruff_cache/*" \
    -x "*.coverage" \
    -x "*htmlcov/*" \
    -x "*.idea/*" \
    -x "*.vscode/*" \
    -x "*.DS_Store" \
    -x "*.env" \
    -x "*.env.local" \
    -x "*.log" \
    -x "dist/*" \
    -x "build/*" \
    -x "*.whl" \
    -x "*.zip" \
    -x "*node_modules/*"

# 清理临时文件
rm -f "$EXCLUDE_FILE"

# 显示结果
echo ""
echo "✅ 打包完成!"
echo ""
echo "📊 文件信息:"
ls -lh "$OUTPUT_FILE"
echo ""
echo "📁 包含的文件数量:"
unzip -l "$OUTPUT_FILE" | tail -1
echo ""
echo "📋 主要目录结构:"
unzip -l "$OUTPUT_FILE" | grep -E '/$' | head -20
