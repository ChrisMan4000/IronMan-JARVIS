# IronMan J.A.R.V.I.S. optional setup: live fan speeds for the HUD (LibreHardwareMonitor).
# Run in a PowerShell opened AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File .\tools\setup-fan-monitor.ps1
# Other install folder: add  -Folder "D:\Tools\LibreHardwareMonitor"
# What it does:
#  1. Writes a small watcher script next to LibreHardwareMonitor.exe (an admin-only folder, because it runs with admin rights).
#  2. Creates the scheduled task "LibreHardwareMonitor Hidden" (no logon trigger). start-jarvis.ps1 starts it;
#     it starts LibreHardwareMonitor hidden and closes it again about 30 seconds after Jarvis has stopped.
#  3. Adds a firewall rule that blocks port 8085 from the network (LibreHardwareMonitor's web server
#     listens on all interfaces without a password; this PC itself can still read it).
param([string]$Folder = 'C:\Program Files\LibreHardwareMonitor')

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "Please run this in a PowerShell that was opened as administrator." -ForegroundColor Red; exit }

$exe = Join-Path $Folder 'LibreHardwareMonitor.exe'
if (-not (Test-Path $exe)) {
  Write-Host "LibreHardwareMonitor.exe was not found in $Folder" -ForegroundColor Red
  Write-Host "Download the zip from https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases, unzip it into that folder and run this script again."
  exit
}

# 1. watcher script
$watch = @'
$exe = '__EXE__'
if (-not (Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue)) { Start-Process $exe -WindowStyle Hidden }
$seen = $false; $down = 0; $start = Get-Date
while ($true) {
  Start-Sleep 2
  $up = [bool](Get-NetTCPConnection -State Listen -LocalPort 8000,8765 -ErrorAction SilentlyContinue)
  if ($up) { $seen = $true; $down = 0 } else { $down++ }
  if ($seen -and $down -ge 3) { break }
  if (-not $seen -and ((Get-Date) - $start).TotalMinutes -gt 5) { break }
}
Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
'@
$watch = $watch.Replace('__EXE__', $exe.Replace("'", "''"))
$wf = Join-Path $Folder 'lhm-watch.ps1'
Set-Content -Path $wf -Value $watch -Encoding UTF8
Write-Host "wrote $wf"

# 2. scheduled task (no trigger, highest privileges, no time limit)
$n = 'LibreHardwareMonitor Hidden'
if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $n -Confirm:$false }
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $wf)
$p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest -LogonType Interactive
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $n -Action $a -Principal $p -Settings $s | Out-Null
Write-Host "created the scheduled task '$n'"

# 3. firewall rule: block port 8085 from the network
$rn = 'Block LHM 8085 from network'
$have = netsh advfirewall firewall show rule name="$rn" | Select-String 'Rule Name'
if (-not $have) {
  netsh advfirewall firewall add rule name="$rn" dir=in action=block protocol=TCP localport=8085 | Out-Null
  Write-Host "added the firewall rule '$rn'"
} else {
  Write-Host "firewall rule '$rn' already exists"
}

Write-Host ""
Write-Host "Done. Next: start Jarvis as usual. In LibreHardwareMonitor's Options menu, 'Remote Web Server > Run' must be on and 'Run On Windows Startup' off." -ForegroundColor Green
