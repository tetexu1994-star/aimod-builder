@echo off
setlocal
cd /d "%~dp0"

echo [1/2] Compiling AIModBuilder.exe ...
set CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe

"%CSC%" /target:winexe /out:AIModBuilder.exe /reference:System.dll,System.Windows.Forms.dll,System.Drawing.dll Launcher.cs
if errorlevel 1 (
    echo [ERROR] Compilation failed.
    pause
    exit /b 1
)

echo [2/2] AIModBuilder.exe built successfully!
pause
