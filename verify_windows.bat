@echo off
chcp 65001 >nul
title AI Mod Builder - 环境健康自检

echo ========================================================
echo   AI Mod Builder - 本机开发环境自检 (Doctor)
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/3] 检查并安装核心运行依赖 (mcp, psutil)...
python -m pip install -r requirements.txt -q

echo.
echo [2/3] 运行环境自检 (Doctor)...
python -m agmod.doctor

echo.
echo [3/3] 运行自动化验证套件 (verify.py)...
python verify.py

pause
