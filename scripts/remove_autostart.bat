@echo off
setlocal
cd /d "%~dp0"

:: 1. Auto-elevate to Administrator for Task Scheduler removal
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ================================================================================
    echo Requesting Administrator privileges to remove Wake Task...
    echo ================================================================================
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

:: 2. Run PowerShell removal script
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0remove_tasks.ps1"
pause

