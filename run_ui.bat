@echo off
chcp 65001 >nul
title AI Mod Builder - 游戏 Mod 工作台

echo ========================================================
echo   AI Mod Builder - 游戏 Mod 制作与安全工作台
echo ========================================================
echo.

set "PY_CMD="

:: 1. 优先使用本地绿色便携 Python (若存在)
if exist "%~dp0runtime\python.exe" (
    set "PY_CMD=%~dp0runtime\python.exe"
    goto :FOUND_PYTHON
)
if exist "%~dp0python\python.exe" (
    set "PY_CMD=%~dp0python\python.exe"
    goto :FOUND_PYTHON
)

:: 2. 检查系统全局 Python
where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :FOUND_PYTHON
)

:: 3. 未检测到 Python，提示选择自动下载或手动安装
echo [提示] 未在系统中检测到 Python 环境。
echo.
echo 是否希望通过 Windows PowerShell 自动下载官方免安装便携版 Python (约 15MB)？
set /p AUTO_INSTALL="按 Y 自动下载便携版，按其他键退出手动安装 (Y/N): "
if /i "%AUTO_INSTALL%"=="Y" (
    echo.
    echo 正在自动下载官方 Python 便携版并解压至 runtime 目录，请稍候...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'; $zip = '%~dp0python_embed.zip'; Invoke-WebRequest -Uri $url -OutFile $zip; Expand-Archive -Path $zip -DestinationPath '%~dp0runtime' -Force; Remove-Item $zip"
    if exist "%~dp0runtime\python.exe" (
        set "PY_CMD=%~dp0runtime\python.exe"
        echo 自动配置便携版 Python 成功！
        goto :FOUND_PYTHON
    ) else (
        echo [错误] 自动下载失败，请手动访问 https://www.python.org/downloads/ 安装 Python 3.10+
        pause
        exit /b 1
    )
) else (
    echo.
    echo 请访问 https://www.python.org/downloads/ 安装 Python 3.10+
    echo 安装时务必勾选 [x] "Add Python to PATH" 选项！
    pause
    exit /b 1
)

:FOUND_PYTHON
echo [1/2] 检查核心依赖 (mcp, psutil)...
"%PY_CMD%" -m pip install -r requirements.txt -q 2>nul || (
    "%PY_CMD%" -c "import psutil" 2>nul || (
        echo 正在通过 pip 安装基础依赖...
        "%PY_CMD%" -m pip install -r requirements.txt
    )
)

echo.
echo [2/2] 启动本地 Web UI 工作台 (http://127.0.0.1:8765)...
echo 浏览器将自动打开。按 Ctrl+C 可停止服务。
echo.
"%PY_CMD%" -m agmod.ui

pause
