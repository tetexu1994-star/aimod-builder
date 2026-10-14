@echo off
setlocal
cd /d "%~dp0"
title AI Mod Builder

if not exist "%~dp0agmod\__init__.py" goto :ERR_EXTRACT

echo Starting AI Mod Builder...

if exist "%~dp0runtime\python.exe" (
    "%~dp0runtime\python.exe" -m agmod.ui
    goto :DONE
)

python -m agmod.ui
if not errorlevel 1 goto :DONE

py -3 -m agmod.ui
if not errorlevel 1 goto :DONE

goto :ERR_PYTHON

:ERR_EXTRACT
echo.
echo [ERROR] Game files missing.
echo Please extract all files from the ZIP before running.
echo.
pause
exit /b 1

:ERR_PYTHON
echo.
echo [ERROR] Python runtime not found.
echo.
pause
exit /b 1

:DONE
if errorlevel 1 pause
