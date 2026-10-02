# Personal Social Media Agent - Task and Shortcut Removal Script
$ErrorActionPreference = "Continue"

Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host "       Removing Personal Social Agent Auto-Start & Wake Tasks..." -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Yellow
Write-Host ""

# 1. Remove Startup shortcuts
$startup = [Environment]::GetFolderPath('Startup')
$oldVbs = Join-Path $startup "PersonalSocialAgent.vbs"
$startupLnk = Join-Path $startup "PersonalSocialAgent.lnk"

if (Test-Path $oldVbs) {
    Remove-Item $oldVbs -Force
    Write-Host "[OK] Removed legacy VBS shortcut."
}
if (Test-Path $startupLnk) {
    Remove-Item $startupLnk -Force
    Write-Host "[OK] Removed Startup folder shortcut."
}

# 2. Remove Desktop shortcut
$desktop = [Environment]::GetFolderPath('Desktop')
$desktopLnk = Join-Path $desktop "Personal Social Agent.lnk"
if (Test-Path $desktopLnk) {
    Remove-Item $desktopLnk -Force
    Write-Host "[OK] Removed Desktop shortcut."
}

# 3. Remove Task Scheduler task
schtasks /Delete /TN "PersonalSocialAgentTask" /F 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Removed Task Scheduler task (PersonalSocialAgentTask)." -ForegroundColor Green
} else {
    Write-Host "[INFO] Task was not found in Task Scheduler (already removed)." -ForegroundColor Gray
}

Write-Host ""
Write-Host "[SUCCESS] Auto-start and wake tasks removed cleanly." -ForegroundColor Green
