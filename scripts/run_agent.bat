@echo off
chcp 65001 >nul
title Personal Social Media Agent - Live Runner
cd /d "%~dp0\.."

echo ================================================================================
echo                     PERSONAL SOCIAL MEDIA AGENT - LIVE RUNNER
echo ================================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
    echo Please set up your Python environment first.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m app.auto_runner

set EXIT_CODE=%errorlevel%
if %EXIT_CODE% neq 0 (
    echo.
    echo [ERROR] Agent stopped with exit code %EXIT_CODE%.
    echo Press any key to close this window...
    pause >nul
) else (
    echo.
    echo [INFO] Agent finished. Window will close in 15 seconds...
    timeout /t 15 >nul
)

