# IronMan J.A.R.V.I.S. uninstaller: removes the whole project from this PC. Run in a normal PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\uninstall-jarvis.ps1
# It shows what it will remove and asks before anything is deleted. It never touches programs
# like Git, Node, uv or LM Studio, and never touches your LM Studio models.
$Repo = $PSScriptRoot
$Cfg  = Join-Path $env:USERPROFILE '.openjarvis'
$Lnk  = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Jarvis.lnk'
function Ask($q) { $a = Read-Host "$q (y/n)"; return ($a -match '^\s*y') }
function SizeGB($p) { if (Test-Path $p) { $b = (Get-ChildItem $p -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum; return [math]::Round($b / 1GB, 2) } return 0 }

# safety: only continue if this really is the project folder
if (-not ((Test-Path "$Repo\start-jarvis.ps1") -and (Test-Path "$Repo\src\openjarvis") -and $Repo.Length -gt 12)) {
  Write-Host "This does not look like the IronMan-JARVIS folder. Nothing was changed." -ForegroundColor Red; exit
}
Write-Host "This will remove:" -ForegroundColor Yellow
Write-Host "  - the project folder  $Repo  ($(SizeGB $Repo) GB)"
Write-Host "  - your settings, Hue key, Tado login and logs  $Cfg  ($(SizeGB $Cfg) GB)"
Write-Host "  - the desktop icon 'Jarvis'"
Write-Host "  - the user settings HUE_BRIDGE_IP and SERPLY_API_KEY"
Write-Host "It will NOT remove Git, uv, Node, Rust, LM Studio or your downloaded models."
$t = Read-Host "Type UNINSTALL to continue (anything else cancels)"
if ($t -cne 'UNINSTALL') { Write-Host "Cancelled. Nothing was changed."; exit }

# 1. stop Jarvis programs (by port: 8000 server, 8765 helper, 8766 wake word, 5173 HUD)
foreach ($port in 8000, 8765, 8766, 5173) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Write-Host "stopped running Jarvis programs"

# 2. icon and user settings
Remove-Item $Lnk -Force -ErrorAction SilentlyContinue
[Environment]::SetEnvironmentVariable('HUE_BRIDGE_IP', $null, 'User')
[Environment]::SetEnvironmentVariable('SERPLY_API_KEY', $null, 'User')
[Environment]::SetEnvironmentVariable('JARVIS_DOC_ROOT', $null, 'User')
Write-Host "removed icon and user settings"

# 3. settings, keys and logs
if (Test-Path $Cfg) { Remove-Item $Cfg -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "removed $Cfg" }

# 3b. optional fan monitor task (only exists if tools\setup-fan-monitor.ps1 was used; removing it needs an administrator window)
if (Get-ScheduledTask -TaskName 'LibreHardwareMonitor Hidden' -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName 'LibreHardwareMonitor Hidden' -Confirm:$false -ErrorAction SilentlyContinue
  if (Get-ScheduledTask -TaskName 'LibreHardwareMonitor Hidden' -ErrorAction SilentlyContinue) {
    Write-Host "The fan monitor task is still there. Run this uninstaller as administrator, or run: Unregister-ScheduledTask -TaskName 'LibreHardwareMonitor Hidden'" -ForegroundColor Yellow
  } else {
    netsh advfirewall firewall delete rule name="Block LHM 8085 from network" | Out-Null
    Write-Host "removed the fan monitor task (LibreHardwareMonitor itself stays installed)"
  }
}

# 4. optional: voice model cache (shared with other Hugging Face programs, so ask)
$hf = Join-Path $env:USERPROFILE '.cache\huggingface\hub\models--hexgrad--Kokoro-82M'
if ((Test-Path $hf) -and (Ask "Also remove the downloaded voice model (Kokoro, $(SizeGB $hf) GB)?")) { Remove-Item $hf -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "removed voice model" }

# 5. the project folder itself (a script cannot delete its own folder while running: a helper does it a moment later)
Write-Host "Removing the project folder in a few seconds..." -ForegroundColor Cyan
Set-Location $env:USERPROFILE
Start-Process cmd -WindowStyle Hidden -ArgumentList '/c', "ping 127.0.0.1 -n 4 >nul & rmdir /s /q `"$Repo`""
Write-Host "Done. Project Jarvis is gone. To remove programs too, use Windows Settings > Apps, or: winget uninstall <name>" -ForegroundColor Green
