@echo off
setlocal
cd /d "%~dp0"

:: 1. Auto-elevate to Administrator if not already running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ================================================================================
    echo Requesting Administrator privileges to register Wake / Sleep Task...
    echo ================================================================================
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

:: 2. Run PowerShell task configurator
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_tasks.ps1"
pause

