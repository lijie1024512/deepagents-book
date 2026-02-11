@echo off
setlocal EnableDelayedExpansion

rem ============================================================
rem  Install deepagents CLI global command (Windows)
rem  Double-click or run in cmd/PowerShell
rem
rem  Usage:
rem    install-cli.bat                # default command: xiaolu
rem    install-cli.bat myapp          # custom command name
rem ============================================================

set "CMD_NAME=%~1"
if "%CMD_NAME%"=="" set "CMD_NAME=xiaolu"

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%") do set "PROJECT_DIR=%%~dpI"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "CLI_PROJECT_DIR=%PROJECT_DIR%\libs\deepagents-cli"

set "INSTALL_DIR=%LOCALAPPDATA%\deepagents\bin"

echo.
echo === deepagents CLI - Global Install ===
echo.
echo   Project : %CLI_PROJECT_DIR%
echo   Install : %INSTALL_DIR%
echo   Command : %CMD_NAME%
echo.

rem Check uv
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv not found. Install it first:
    echo   https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

rem Create install dir
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

rem Write wrapper .cmd (for cmd.exe / PowerShell)
> "%INSTALL_DIR%\%CMD_NAME%.cmd" (
    echo @echo off
    echo uv run --project "%CLI_PROJECT_DIR%" deepagents %%*
)

echo [OK] Created: %INSTALL_DIR%\%CMD_NAME%.cmd

rem Write bash wrapper (for Git Bash / MINGW / WSL)
rem Convert backslashes to forward slashes for bash compatibility
set "CLI_PROJECT_BASH=%CLI_PROJECT_DIR:\=/%"
> "%INSTALL_DIR%\%CMD_NAME%" (
    echo #!/bin/bash
    echo exec uv run --project "%CLI_PROJECT_BASH%" deepagents "$@"
)

echo [OK] Created: %INSTALL_DIR%\%CMD_NAME%  (Git Bash)
echo.

rem Add to user PATH if needed
echo %PATH% | findstr /i /c:"%INSTALL_DIR%" >nul 2>&1
if errorlevel 1 (
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
    if "!USER_PATH!"=="" (
        setx Path "%INSTALL_DIR%" >nul 2>&1
    ) else (
        setx Path "%INSTALL_DIR%;!USER_PATH!" >nul 2>&1
    )
    set "PATH=%INSTALL_DIR%;%PATH%"
    echo [OK] Added %INSTALL_DIR% to user PATH
    echo     Open a new terminal for it to take effect.
    echo.
)

rem Verify
echo Verifying...
uv run --project "%CLI_PROJECT_DIR%" deepagents --version
if errorlevel 1 (
    echo [WARN] Verification failed. Check uv and project dependencies.
) else (
    echo [OK] Verified.
)

echo.
echo ============================================================
echo  Done! You can now use from any directory:
echo.
echo    %CMD_NAME%                     Start interactive mode
echo    %CMD_NAME% -r                  Resume last session
echo    %CMD_NAME% -r ^<id^>             Resume specific session
echo    %CMD_NAME% -m "hello"          Single message
echo    %CMD_NAME% novel init "title"  Novel mode
echo ============================================================
echo.
pause
