# IronMan J.A.R.V.I.S. optional setup: live fan speeds for the HUD (LibreHardwareMonitor).
# Run in a PowerShell opened AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File .\tools\setup-fan-monitor.ps1
# Other install folder: add  -Folder "D:\Tools\LibreHardwareMonitor"
# What it does:
#  1. Writes a small watcher script next to LibreHardwareMonitor.exe (an admin-only folder, because it runs with admin rights).
#  2. Creates the scheduled task "LibreHardwareMonitor Hidden" (no logon trigger). start-jarvis.ps1 starts it;
#     it starts LibreHardwareMonitor hidden and keeps it running until you use Stop Jarvis (which drops a flag file the watcher is waiting for).
#  3. Adds a firewall rule that blocks port 8085 from the network (LibreHardwareMonitor's web server
#     listens on all interfaces without a password; this PC itself can still read it).
# Exit code 0 when the task and the firewall rule exist afterwards, 1 otherwise (tools\install-fan-monitor.ps1 checks it).
param([string]$Folder = 'C:\Program Files\LibreHardwareMonitor')
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
if (-not (Test-IsAdministrator)) { Write-Host "Please run this in a PowerShell that was opened as administrator." -ForegroundColor Red; exit 1 }

$exe = Join-Path $Folder 'LibreHardwareMonitor.exe'
if (-not (Test-Path $exe)) {
  Write-Host "LibreHardwareMonitor.exe was not found in $Folder" -ForegroundColor Red
  Write-Host "Download the zip from https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases, unzip it into that folder and run this script again."
  exit 1
}

# 1. watcher script (runs on its own with administrator rights, so it gets the values written in instead of reading the project files)
$watch = @'
$exe = '__EXE__'
$flag = '__FLAG__'
Remove-Item $flag -ErrorAction SilentlyContinue
if (-not (Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue)) { Start-Process $exe -WindowStyle Hidden }
Start-Sleep 3
while ((Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue) -and -not (Test-Path $flag)) { Start-Sleep 2 }
Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item $flag -ErrorAction SilentlyContinue
'@
$watch = $watch.Replace('__EXE__', $exe.Replace("'", "''")).Replace('__FLAG__', (Join-Path $JarvisConfigDir 'stop-lhm.flag').Replace("'", "''"))   # Stop Jarvis (tools\stop-jarvis.ps1) creates this flag file; the watcher then closes LibreHardwareMonitor
$wf = Join-Path $Folder 'lhm-watch.ps1'
Set-Content -Path $wf -Value $watch -Encoding UTF8
Write-Host "wrote $wf"

# 2. scheduled task (no trigger, highest privileges, no time limit)
$n = $JarvisFanTaskName
if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $n -Confirm:$false }
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $wf)
$p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest -LogonType Interactive
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $n -Action $a -Principal $p -Settings $s | Out-Null
if (-not (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)) { Write-Host "The scheduled task '$n' could not be created." -ForegroundColor Red; exit 1 }
Write-Host "created the scheduled task '$n'"

# 3. firewall rule: block port 8085 from the network
$rn = $JarvisFanFirewallRule
netsh advfirewall firewall show rule name="$rn" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  netsh advfirewall firewall add rule name="$rn" dir=in action=block protocol=TCP localport=8085 | Out-Null
  if ($LASTEXITCODE -ne 0) { Write-Host "The firewall rule '$rn' could not be added (code $LASTEXITCODE)." -ForegroundColor Red; exit 1 }
  Write-Host "added the firewall rule '$rn'"
} else {
  Write-Host "firewall rule '$rn' already exists"
}

Write-Host ""
Write-Host "Done. Next: start Jarvis as usual. In LibreHardwareMonitor's Options menu, 'Remote Web Server > Run' must be on and 'Run On Windows Startup' off." -ForegroundColor Green
exit 0
