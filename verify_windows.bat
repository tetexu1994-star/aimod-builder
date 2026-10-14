@echo off
chcp 65001 >nul
title AI Mod Builder - 环境健康自检

echo ========================================================
echo   AI Mod Builder - 本机开发环境自检 (Doctor)
echo ========================================================
echo.

set "PY_CMD="

if exist "%~dp0runtime\python.exe" (
    set "PY_CMD=%~dp0runtime\python.exe"
    goto :FOUND_PYTHON
)
if exist "%~dp0python\python.exe" (
    set "PY_CMD=%~dp0python\python.exe"
    goto :FOUND_PYTHON
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :FOUND_PYTHON
)

echo [错误] 未检测到 Python，请先运行 run_ui.bat 自动配置或手动安装 Python 3.10+
pause
exit /b 1

:FOUND_PYTHON
echo [1/3] 检查并安装核心运行依赖 (mcp, psutil)...
"%PY_CMD%" -m pip install -r requirements.txt -q

echo.
echo [2/3] 运行环境自检 (Doctor)...
"%PY_CMD%" -m agmod.doctor

echo.
echo [3/3] 运行自动化验证套件 (verify.py)...
"%PY_CMD%" verify.py

pause
