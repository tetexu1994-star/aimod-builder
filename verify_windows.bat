@echo off
setlocal
cd /d "%~dp0"
title AI Mod Builder - 环境健康自检

echo ========================================================
echo   AI Mod Builder - 本机开发环境自检 (Doctor)
echo ========================================================
echo.

if not exist "%~dp0agmod\__init__.py" (
    echo [错误] 请先解压整个 ZIP 压缩包后再运行！
    pause
    exit /b 1
)

set "PY_CMD="

if exist "%~dp0runtime\python.exe" (
    "%~dp0runtime\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=%~dp0runtime\python.exe"
)

if not defined PY_CMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo [错误] 未检测到有效的 Python 环境。请先运行 run_ui.bat 自动配置或手动安装 Python。
    pause
    exit /b 1
)

echo [就绪] 使用 Python 解释器: %PY_CMD%
echo.
echo [1/2] 运行环境健康自检 (Doctor)...
%PY_CMD% -m agmod.doctor

echo.
echo [2/2] 运行功能自动化验证套件 (verify.py)...
%PY_CMD% verify.py

echo.
pause
