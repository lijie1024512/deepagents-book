#!/bin/bash
#
# 打包 deepagents-book 整个项目为 zip 文件
#
# ============================================================
# 打包命令:
# ============================================================
#   cd /home/lijie/test/deepagents-book
#   ./scripts/pack.sh                  # 输出 deepagents-book.zip
#   ./scripts/pack.sh my-release       # 输出 my-release.zip
#
# ============================================================
# 启动 deepagents-cli (小说创作模式):
# ============================================================
#   # 1. 进入 CLI 目录并安装依赖
#   cd /home/lijie/test/deepagents-book/libs/deepagents-cli
#   uv sync --all-groups
#
#   # 2. 启动 CLI（推荐：直接通过自然语言交互）
#   cd /home/lijie/test/deepagents-book/novels
#   uv run --project ../libs/deepagents-cli deepagents
#
#   然后直接说：
#   - "我想写一本海贼王同人小说"  → 自动创建项目
#   - "帮我设计一下主角"          → 引导角色设计
#   - "开始写第一章大纲"          → 生成大纲
#   - "根据大纲写正文"            → 生成正文
#   - "这段节奏太快了"            → 优化调整
#
#   # 或者使用命令行方式初始化：
#   uv run --project ../libs/deepagents-cli deepagents novel init "我的小说" --world onepiece
#   cd 我的小说
#   uv run --project ../../libs/deepagents-cli deepagents novel start
#
# ============================================================
# 提示词优化功能:
# ============================================================
#   默认情况下，提示词优化不会自动触发。
#   如需优化提示词，在消息开头添加 @优化 或 @opt 标记：
#
#   @优化 帮我写个海贼王同人小说
#   @opt 写一个穿越到火影世界的故事
#
#   不带标记的普通对话不会触发优化：
#   帮我看看第三章的大纲   (正常处理，不优化)
#
# ============================================================
# 对话日志功能:
# ============================================================
#   日志记录所有用户问题和AI回答，保存为Markdown格式。
#
#   日志存储位置: ~/.deepagents/logs/{thread_id}.md
#
#   查看日志命令:
#   xiaolu logs list              # 列出所有日志
#   xiaolu logs view <id>         # 查看指定日志
#   xiaolu logs path              # 显示日志目录路径
#
#   在TUI界面中:
#   /logs                         # 查看当前日志信息
#   /logs <thread_id>             # 查看指定日志内容
#
# ============================================================
# 全局安装 CLI (任意目录直接输入 xiaolu 启动):
# ============================================================
#
#   --- Linux / macOS ---
#   cd /home/lijie/test/deepagents-book
#   ./scripts/install-cli.sh                    # 安装为 xiaolu 到 ~/.local/bin/
#   ./scripts/install-cli.sh /usr/local/bin      # 指定安装目录
#   ./scripts/install-cli.sh ~/.local/bin myapp  # 自定义命令名
#
#   --- Windows (双击或命令行) ---
#   scripts\install-cli.bat              # 双击运行，安装为 xiaolu
#   scripts\install-cli.bat myapp        # 自定义命令名
#
#   安装后即可在任意目录使用:
#   xiaolu                    # 启动交互模式
#   xiaolu -m '你好'           # 单次消息
#   xiaolu novel init '标题'   # 小说模式
#
# ============================================================
# 会话恢复 (历史记录):
# ============================================================
#   每次 xiaolu 启动默认创建新会话 (新 thread ID)。
#   如需继续之前的对话，使用 -r / --resume 参数:
#
#   xiaolu -r                 # 恢复最近一次会话
#   xiaolu -r <thread_id>     # 恢复指定会话
#
#   查看历史会话:
#   xiaolu logs list          # 列出所有会话日志
#   xiaolu logs view <id>     # 查看指定会话内容
#
# ============================================================
# 排除内容:
# ============================================================
#   - .git/, .venv/, venv/, __pycache__/
#   - *.pyc, *.pyo, *.egg-info/, dist/, build/
#   - .pytest_cache/, .mypy_cache/, .ruff_cache/
#   - node_modules/, *.log, .env, *.db
#   - novels/, .claude/ (生成的数据)
#

set -e

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="deepagents-book"

# 输出文件名
OUTPUT_NAME="${1:-${PROJECT_NAME}}"
OUTPUT_FILE="${PROJECT_DIR}/${OUTPUT_NAME}.zip"

echo "📦 打包项目: $PROJECT_NAME"
echo "   源目录: $PROJECT_DIR"
echo "   输出文件: $OUTPUT_FILE"
echo ""

# 切换到项目目录
cd "$PROJECT_DIR"

# 执行打包
echo "🔍 排除以下内容:"
echo "   - .git/, .venv/, venv/, __pycache__/"
echo "   - *.pyc, *.pyo, *.egg-info/"
echo "   - .pytest_cache/, .mypy_cache/, .ruff_cache/"
echo "   - node_modules/, dist/, build/"
echo "   - *.log, .env, .coverage"
echo ""

# 使用 zip 打包，排除不需要的文件
zip -r "$OUTPUT_FILE" . \
    -x "*.git/*" \
    -x "*__pycache__/*" \
    -x "*.pyc" \
    -x "*.pyo" \
    -x "*.pyd" \
    -x "*.so" \
    -x "*.egg-info/*" \
    -x "*.eggs/*" \
    -x "*.venv/*" \
    -x "*venv/*" \
    -x "*/.venv/*" \
    -x "*/venv/*" \
    -x "*.pytest_cache/*" \
    -x "*.mypy_cache/*" \
    -x "*.ruff_cache/*" \
    -x "*.tox/*" \
    -x "*.nox/*" \
    -x "*.coverage" \
    -x "*htmlcov/*" \
    -x "*.idea/*" \
    -x "*.vscode/*" \
    -x "*.DS_Store" \
    -x "*.env" \
    -x "*.env.local" \
    -x "*.log" \
    -x "*dist/*" \
    -x "*build/*" \
    -x "*.whl" \
    -x "*.zip" \
    -x "*node_modules/*" \
    -x "*.db" \
    -x "*.db-wal" \
    -x "*.db-shm" \
    -x "*novels/*" \
    -x "*.claude/*"

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
echo "📋 顶层目录结构:"
unzip -l "$OUTPUT_FILE" | grep -E '^.*0.*[0-9]{2}:[0-9]{2}   [^/]+/$' | head -20
