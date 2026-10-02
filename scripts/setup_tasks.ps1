# Personal Social Media Agent - Task and Shortcut Setup Script
$ErrorActionPreference = "Continue"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "     Personal Social Media Agent - Auto-Start & Wake Configuration" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$targetBat = Join-Path $scriptDir "run_agent.bat"
$xmlPath = Join-Path $scriptDir "agent_task.xml"

$ws = New-Object -ComObject WScript.Shell

# 1. Startup folder shortcut (runs on Boot / User Login)
try {
    $startup = [Environment]::GetFolderPath('Startup')
    $oldVbs = Join-Path $startup "PersonalSocialAgent.vbs"
    if (Test-Path $oldVbs) {
        Remove-Item $oldVbs -Force
        Write-Host "[OK] Removed legacy silent VBS shortcut." -ForegroundColor Gray
    }

    $startupLnk = Join-Path $startup "PersonalSocialAgent.lnk"
    $s = $ws.CreateShortcut($startupLnk)
    $s.TargetPath = $targetBat
    $s.WorkingDirectory = $projectDir
    $s.Description = "Personal Social Agent Live Runner"
    $s.Save()
    Write-Host "[SUCCESS] Windows Startup shortcut configured!" -ForegroundColor Green
    Write-Host "  -> $startupLnk" -ForegroundColor DarkGray
} catch {
    Write-Host "[WARNING] Could not create Startup shortcut: $_" -ForegroundColor Yellow
}

# 2. Desktop shortcut for easy manual launch
try {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $desktopLnk = Join-Path $desktop "Personal Social Agent.lnk"
    $s = $ws.CreateShortcut($desktopLnk)
    $s.TargetPath = $targetBat
    $s.WorkingDirectory = $projectDir
    $s.Description = "Personal Social Agent Live Runner"
    $s.Save()
    Write-Host "[SUCCESS] Desktop shortcut created on Desktop!" -ForegroundColor Green
    Write-Host "  -> $desktopLnk" -ForegroundColor DarkGray
} catch {
    Write-Host "[WARNING] Could not create Desktop shortcut: $_" -ForegroundColor Yellow
}

# 3. Windows Task Scheduler (Wake from Sleep, Screen Unlock, User Logon)
Write-Host ""
Write-Host "Registering Windows Task Scheduler task (PersonalSocialAgentTask)..." -ForegroundColor Cyan

$tempXml = [System.IO.Path]::GetTempFileName()
$xmlContent = Get-Content -Raw $xmlPath
Set-Content -Path $tempXml -Value $xmlContent -Encoding Unicode

$res = schtasks /Create /TN "PersonalSocialAgentTask" /XML $tempXml /F 2>&1
Remove-Item $tempXml -ErrorAction SilentlyContinue

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] Windows Task Scheduler successfully registered!" -ForegroundColor Green
    Write-Host "  - Triggers on Laptop Lid Open / Resume from Sleep" -ForegroundColor White
    Write-Host "  - Triggers on Screen Unlock" -ForegroundColor White
    Write-Host "  - Triggers on Boot / User Logon" -ForegroundColor White
    Write-Host "  - Displays a LIVE CMD window so you can watch progress in real time!" -ForegroundColor White
} else {
    Write-Host "[ERROR] Task Scheduler registration returned error code $LASTEXITCODE :" -ForegroundColor Red
    Write-Host "$res" -ForegroundColor Red
    Write-Host "To register Wake-from-sleep, please right-click setup_autostart.bat and select 'Run as Administrator'." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "Setup Complete! You can test now by double-clicking 'Personal Social Agent' on Desktop." -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
