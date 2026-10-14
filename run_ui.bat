@echo off
chcp 65001 >nul
title AI Mod Builder - 游戏 Mod 工作台

echo ========================================================
echo   AI Mod Builder - 游戏 Mod 制作与安全工作台
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/2] 检查并安装核心运行依赖 (mcp, psutil)...
python -m pip install -r requirements.txt -q

echo.
echo [2/2] 启动本地 Web UI 工作台 (http://127.0.0.1:8765)...
echo 浏览器将自动打开。按 Ctrl+C 可停止服务。
echo.
python -m agmod.ui

pause
