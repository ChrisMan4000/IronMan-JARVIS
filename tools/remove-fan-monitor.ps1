# IronMan J.A.R.V.I.S.: removes the fan monitor that tools\install-fan-monitor.ps1 set up (needs administrator rights; the uninstaller asks Windows for them).
# Removes: the scheduled task "LibreHardwareMonitor Hidden", the firewall rule "Block LHM 8085 from network" and the LibreHardwareMonitor folder
# - but the folder ONLY if it carries the marker file written by install-fan-monitor.ps1 (a LibreHardwareMonitor you installed yourself is never deleted).
param([string]$Folder = 'C:\Program Files\LibreHardwareMonitor')
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "Please run this as administrator."; exit 1 }
$marker = Join-Path $Folder 'installed-by-ironman-jarvis.txt'
if (-not (Test-Path $marker)) { Write-Host "No marker file: this LibreHardwareMonitor was not installed by IronMan J.A.R.V.I.S., nothing removed."; exit 0 }
Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
$n = 'LibreHardwareMonitor Hidden'
if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $n -Confirm:$false }
netsh advfirewall firewall delete rule name="Block LHM 8085 from network" | Out-Null
Start-Sleep -Seconds 1
Remove-Item $Folder -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path $Folder) { Write-Host "Could not remove everything in $Folder (a file is still in use?)."; exit 2 }
Write-Host "Fan monitor removed."
exit 0
