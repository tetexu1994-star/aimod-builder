@echo off
setlocal
cd /d "%~dp0"
title AI Mod Builder - 游戏 Mod 工作台

echo ========================================================
echo   AI Mod Builder - 游戏 Mod 制作与安全工作台
echo ========================================================
echo.

:: 0. 检查是否在压缩包内部直接运行
if not exist "%~dp0agmod\__init__.py" (
    echo [错误] 请先将整个 ZIP 压缩包【解压到文件夹】后再运行！
    echo 请不要直接在压缩包内双击，否则会缺少核心代码文件。
    echo.
    pause
    exit /b 1
)

:: 1. 寻找可用的 Python 解释器
set "PY_CMD="

:: 优先检查自带的便携版
if exist "%~dp0runtime\python.exe" (
    "%~dp0runtime\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=%~dp0runtime\python.exe"
        goto :FOUND_PY
    )
)

:: 检查系统 python
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :FOUND_PY
)

:: 检查系统 py 启动器
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :FOUND_PY
)

:: 2. 未找到有效 Python
echo [提示] 未检测到有效的 Python 环境。
echo (注: Windows 商店的空替身快捷方式已被过滤)
echo.
echo 是否希望自动下载官方免安装 Python 绿色便携版 (约 15MB)？
echo.
set "USER_CHOICE="
set /p USER_CHOICE="输入 Y 自动下载便携版，直接按回车退出手动安装 [Y/N]: "

if /i "%USER_CHOICE%"=="Y" (
    echo.
    echo 正在自动下载 Python 便携版并解压至 runtime 目录，请稍候...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'; $zip = '%~dp0python_embed.zip'; Invoke-WebRequest -Uri $url -OutFile $zip; Expand-Archive -Path $zip -DestinationPath '%~dp0runtime' -Force; Remove-Item $zip -Force"
    if exist "%~dp0runtime\python.exe" (
        set "PY_CMD=%~dp0runtime\python.exe"
        echo 自动配置便携版 Python 成功！
        goto :FOUND_PY
    )
    echo [错误] 自动下载失败，网络可能受限。
)

echo.
echo ========================================================
echo 请先安装 Python 3.10+：
echo 1. 访问官网下载: https://www.python.org/downloads/
echo 2. 安装时请务必勾选 [x] "Add python.exe to PATH"
echo ========================================================
echo.
pause
exit /b 1

:FOUND_PY
echo [就绪] 使用 Python 解释器: %PY_CMD%
echo.

:: 3. 启动 UI (agmod.ui 完全依赖标准库，零外部包即可直接运行)
echo 正在启动本地 Web 工作台 (http://127.0.0.1:8765)...
echo 浏览器将自动打开。按 Ctrl+C 可停止服务。
echo.

%PY_CMD% -m agmod.ui

if errorlevel 1 (
    echo.
    echo [错误] 工作台启动失败或异常退出。
)

echo.
pause
