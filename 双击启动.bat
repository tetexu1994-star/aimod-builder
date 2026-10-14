@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title AI Mod Builder - 游戏 Mod 工作台

echo ========================================================
echo   AI Mod Builder - 游戏 Mod 制作与安全工作台
echo ========================================================
echo.

REM 0. 检查是否在压缩包内部直接运行
if not exist "%~dp0agmod\__init__.py" (
    echo [错误] 请先解压整个 ZIP 压缩包后再运行！不要在压缩包内直接双击。
    echo.
    pause
    exit /b 1
)

REM 1. 优先使用随包自带的免安装 Python 绿色环境
set "PY_CMD="

if exist "%~dp0runtime\python.exe" (
    set "PY_CMD=%~dp0runtime\python.exe"
    goto :FOUND_PY
)

REM 2. 检查系统全局 python
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :FOUND_PY
)

REM 3. 检查系统 py -3 启动器
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :FOUND_PY
)

REM 4. 未找到有效 Python
echo [错误] 未检测到 Python 运行环境。
echo.
echo 解决方案：
echo 1. 请下载包含免安装运行时的完整便携版 (自带 runtime 文件夹)；
echo 2. 或访问 https://www.python.org/downloads/ 安装 Python 3.10+ (记得勾选 Add to PATH)。
echo.
pause
exit /b 1

:FOUND_PY
echo [就绪] 使用 Python 解释器: %PY_CMD%
echo.
echo 正在启动 Web 工作台 (http://127.0.0.1:8765)...
echo 默认浏览器将自动打开。按 Ctrl+C 可停止服务。
echo.

"%PY_CMD%" -m agmod.ui

if errorlevel 1 (
    echo.
    echo [错误] 工作台异常退出，请查看上方报错信息。
)

echo.
pause
