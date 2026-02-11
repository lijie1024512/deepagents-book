#!/bin/bash
#
# 安装 deepagents CLI 全局命令
# 安装后在任意目录输入 xiaolu 即可启动
#
# 用法:
#   ./scripts/install-cli.sh                    # 安装到 ~/.local/bin/，命令名 xiaolu
#   ./scripts/install-cli.sh /usr/local/bin      # 安装到指定目录
#   ./scripts/install-cli.sh ~/.local/bin myapp  # 自定义命令名
#

set -e

# 定位项目根目录 (基于脚本自身位置)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLI_PROJECT_DIR="$PROJECT_DIR/libs/deepagents-cli"

# 安装目标目录 和 命令名
INSTALL_DIR="${1:-$HOME/.local/bin}"
CMD_NAME="${2:-xiaolu}"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== deepagents CLI 全局安装 ==="
echo ""
echo "  项目目录: $CLI_PROJECT_DIR"
echo "  安装目录: $INSTALL_DIR"
echo "  命令名称: $CMD_NAME"
echo ""

# 检查 uv 是否安装
if ! command -v uv &> /dev/null; then
    echo "错误: 未找到 uv，请先安装: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# 确保目标目录存在
mkdir -p "$INSTALL_DIR"

# 创建包装脚本
cat > "$INSTALL_DIR/$CMD_NAME" << WRAPPER
#!/bin/bash
# deepagents CLI 全局启动器 (自动生成，勿手动编辑)
# 项目路径: $CLI_PROJECT_DIR
exec uv run --project "$CLI_PROJECT_DIR" deepagents "\$@"
WRAPPER

chmod +x "$INSTALL_DIR/$CMD_NAME"

# 检查 PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo -e "${YELLOW}提示: $INSTALL_DIR 不在 PATH 中${NC}"
    echo ""
    echo "请将以下内容添加到你的 shell 配置文件 (~/.bashrc 或 ~/.zshrc):"
    echo ""
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    echo ""
    echo "然后执行:"
    echo "  source ~/.bashrc   # 或 source ~/.zshrc"
    echo ""
else
    echo -e "${GREEN}安装成功!${NC}"
    echo ""
    echo "现在可以在任意目录使用:"
    echo "  $CMD_NAME                    # 启动交互模式"
    echo "  $CMD_NAME -m '你好'           # 单次消息"
    echo "  $CMD_NAME novel init '标题'   # 小说模式"
    echo ""
fi
