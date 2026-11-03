# IronMan J.A.R.V.I.S. uninstaller for a setup made with install-jarvis.ps1 (the Windows installer .exe has its own uninstaller).
# Removes the whole project from this PC. Run in a normal PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\uninstall-jarvis.ps1
# It shows what it will remove and asks before anything is deleted. It never touches programs
# like Git, Node, uv or LM Studio, and never touches your LM Studio models.
# Exit codes: 0 = removed (or cancelled by you), 1 = this is not the project folder, nothing was changed.
$Repo = $PSScriptRoot
. (Join-Path $Repo 'tools\jarvis-common.ps1')
$desk = [Environment]::GetFolderPath('Desktop')
$shortcuts = (Join-Path $desk 'Jarvis.lnk'), (Join-Path $desk 'Stop Jarvis.lnk')
$voiceCache = Join-Path $env:USERPROFILE '.cache\huggingface\hub\models--hexgrad--Kokoro-82M'
$lhmMarker = 'C:\Program Files\LibreHardwareMonitor\installed-by-ironman-jarvis.txt'
function Get-FolderSizeGB([string]$Path) {
  if (-not (Test-Path $Path)) { return 0 }
  $b = (Get-ChildItem $Path -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  return [math]::Round($b / 1GB, 2)
}

# safety: only continue if this really is the project folder (the folder is deleted recursively at the end)
if (-not (Test-JarvisProjectFolder $Repo)) { Write-Host "This does not look like the IronMan-JARVIS folder. Nothing was changed." -ForegroundColor Red; exit 1 }
# parts in Windows itself that need administrator rights to remove (fan monitor, LAN gateway firewall rule)
netsh advfirewall firewall show rule name="$JarvisGatewayFirewallRule" 2>&1 | Out-Null; $gatewayRule = ($LASTEXITCODE -eq 0)
$windowsParts = $gatewayRule -or (Test-Path $lhmMarker) -or [bool](Get-ScheduledTask -TaskName $JarvisFanTaskName -ErrorAction SilentlyContinue)

Write-Host "This will remove:" -ForegroundColor Yellow
Write-Host "  - the project folder  $Repo  ($(Get-FolderSizeGB $Repo) GB)"
Write-Host "  - your settings, Hue key, Tado login, LAN gateway password and logs  $JarvisConfigDir  ($(Get-FolderSizeGB $JarvisConfigDir) GB)"
Write-Host "  - the desktop icons 'Jarvis' and 'Stop Jarvis'"
Write-Host "  - the user settings $($JarvisUserEnvVars -join ', ')"
if ($windowsParts) { Write-Host "  - the fan monitor task and LibreHardwareMonitor (only if this setup installed it) and the firewall rules for ports 8085/8443 (Windows asks for administrator permission)" }
Write-Host "It will NOT remove Git, uv, Node, Rust, LM Studio or your downloaded models."
$t = Read-Host "Type UNINSTALL to continue (anything else cancels)"
if ($t -cne 'UNINSTALL') { Write-Host "Cancelled. Nothing was changed."; exit 0 }

# 1. stop Jarvis (supervisor first, then every service and the server; LM Studio stays as it is)
& (Join-Path $Repo 'tools\stop-jarvis.ps1') -KeepLmStudio
if ($LASTEXITCODE -ne 0) { Write-Host "Some Jarvis programs are still running; files in use may stay behind." -ForegroundColor Yellow }

# 2. parts in Windows itself (one administrator prompt)
if ($windowsParts) {
  try {
    $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $Repo 'tools\remove-windows-parts.ps1'))
    if ($p.ExitCode -eq 0) { Write-Host "removed the fan monitor and firewall rules" }
    else { Write-Host "Not everything in Windows could be removed. Run as administrator: powershell -ExecutionPolicy Bypass -File `"$Repo\tools\remove-windows-parts.ps1`" (before the folder is gone, or from a fresh clone)" -ForegroundColor Yellow }
  } catch { Write-Host "Administrator permission was not given: the fan monitor task and the firewall rules stay. To remove them later, run tools\remove-windows-parts.ps1 as administrator (from a fresh clone)." -ForegroundColor Yellow }
}

# 3. icons and user settings
Remove-Item $shortcuts -Force -ErrorAction SilentlyContinue
foreach ($n in $JarvisUserEnvVars) { [Environment]::SetEnvironmentVariable($n, $null, 'User') }
Write-Host "removed icons and user settings"

# 4. settings, keys and logs
if (Test-Path $JarvisConfigDir) { Remove-Item $JarvisConfigDir -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "removed $JarvisConfigDir" }

# 5. optional: voice model cache (shared with other Hugging Face programs, so ask)
if ((Test-Path $voiceCache) -and (Read-YesNo "Also remove the downloaded voice model (Kokoro, $(Get-FolderSizeGB $voiceCache) GB)?")) { Remove-Item $voiceCache -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "removed voice model" }

# 6. the project folder itself (a script cannot delete its own folder while running: a helper does it a moment later)
Write-Host "Removing the project folder in a few seconds..." -ForegroundColor Cyan
Set-Location $env:USERPROFILE
Start-Process cmd -WindowStyle Hidden -ArgumentList '/c', "ping 127.0.0.1 -n 4 >nul & rmdir /s /q `"$Repo`""
Write-Host "Done. Project Jarvis is gone. To remove programs too, use Windows Settings > Apps, or: winget uninstall <name>" -ForegroundColor Green
exit 0
