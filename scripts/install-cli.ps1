#
# 安装 deepagents CLI 全局命令 (Windows PowerShell)
# 安装后在任意目录输入 xiaolu 即可启动
#
# 用法 (以管理员或普通用户运行 PowerShell):
#   .\scripts\install-cli.ps1                                  # 默认命令名 xiaolu
#   .\scripts\install-cli.ps1 -CmdName "myapp"                 # 自定义命令名
#   .\scripts\install-cli.ps1 -InstallDir "C:\tools"           # 指定安装目录
#   .\scripts\install-cli.ps1 -InstallDir "C:\tools" -CmdName "da"  # 都自定义
#

param(
    [string]$InstallDir = "",
    [string]$CmdName = "xiaolu"
)

$ErrorActionPreference = "Stop"

# 定位项目根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$CliProjectDir = Join-Path $ProjectDir "libs" "deepagents-cli"

# 默认安装目录: ~/AppData/Local/deepagents/bin (用户级别，无需管理员)
if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "deepagents" "bin"
}

Write-Host "=== deepagents CLI 全局安装 (Windows) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  项目目录: $CliProjectDir"
Write-Host "  安装目录: $InstallDir"
Write-Host "  命令名称: $CmdName"
Write-Host ""

# 检查 uv 是否安装
$uvPath = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvPath) {
    Write-Host "错误: 未找到 uv，请先安装: https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor Red
    Write-Host "  PowerShell 安装: irm https://astral.sh/uv/install.ps1 | iex"
    exit 1
}

# 确保目标目录存在
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# 创建 .cmd 包装脚本 (cmd.exe 兼容)
$CmdWrapper = Join-Path $InstallDir "$CmdName.cmd"
$CmdContent = @"
@echo off
rem deepagents CLI 全局启动器 (自动生成，勿手动编辑)
rem 项目路径: $CliProjectDir
uv run --project "$CliProjectDir" deepagents %*
"@
Set-Content -Path $CmdWrapper -Value $CmdContent -Encoding ASCII

# 创建 PowerShell 包装脚本
$Ps1Wrapper = Join-Path $InstallDir "$CmdName.ps1"
$Ps1Content = @"
# deepagents CLI 全局启动器 (自动生成，勿手动编辑)
# 项目路径: $CliProjectDir
& uv run --project "$CliProjectDir" deepagents @args
"@
Set-Content -Path $Ps1Wrapper -Value $Ps1Content -Encoding UTF8

Write-Host "已创建:" -ForegroundColor Green
Write-Host "  $CmdWrapper      (cmd / Terminal)"
Write-Host "  $Ps1Wrapper      (PowerShell)"
Write-Host ""

# 检查并添加 PATH
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$InstallDir*") {
    $NewPath = "$InstallDir;$UserPath"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    # 同时更新当前会话的 PATH
    $env:Path = "$InstallDir;$env:Path"
    Write-Host "已将 $InstallDir 添加到用户 PATH" -ForegroundColor Yellow
    Write-Host "新的终端窗口会自动生效，当前窗口也已更新。" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "安装成功!" -ForegroundColor Green
Write-Host ""
Write-Host "现在可以在任意目录使用:" -ForegroundColor Cyan
Write-Host "  $CmdName                    # 启动交互模式"
Write-Host "  $CmdName -m '你好'           # 单次消息"
Write-Host "  $CmdName novel init '标题'   # 小说模式"
Write-Host ""

# 验证
Write-Host "验证安装:" -ForegroundColor Cyan
try {
    & uv run --project "$CliProjectDir" deepagents --version
    Write-Host "  OK" -ForegroundColor Green
} catch {
    Write-Host "  警告: 验证失败，请检查 uv 和项目依赖是否正确" -ForegroundColor Yellow
}
