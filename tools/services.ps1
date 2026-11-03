# Jarvis services supervisor: runs the helper programs hidden in ONE terminal tab (started by start-jarvis.ps1) and restarts any that stop.
# Services: helper 8765 (hwstats.py), HUD web server 5173 (Vite), wake word 8766 (only if set up), backup watcher (only if present),
# LAN gateway 8443 (only after tools\setup-remote-access.ps1). Logs: %USERPROFILE%\.openjarvis\logs (one .out.log and .err.log per service).
# Stop everything with tools\stop-jarvis.ps1. Try it without starting anything: powershell -File tools\services.ps1 -WhatIf
[CmdletBinding(SupportsShouldProcess = $true)]
param()
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $JarvisConfigDir 'logs'
New-Item -ItemType Directory -Force $log | Out-Null
# keep the console quiet: harmless library warnings are not shown (full errors still go to the log files)
$env:PYTHONWARNINGS = 'ignore'
$env:HF_HUB_VERBOSITY = 'error'

# one entry per helper program: name (also the log file name), program, arguments, working folder
$services = @()
if (Test-Path "$root\tools\backup-watch.ps1") { $services += @{ Name = 'backup'; File = 'powershell.exe'; Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$root\tools\backup-watch.ps1`""; Folder = $root } }   # optional personal backup, not in the public repo
$services += @{ Name = 'helper-8765'; File = 'uv'; Arguments = 'run --no-sync python tools\hwstats.py'; Folder = $root }
$wakePy = "$root\tools\npu\.venv\Scripts\python.exe"
if (Test-WakeWordReady "$root\tools\npu") { $services += @{ Name = 'wake-8766'; File = $wakePy; Arguments = 'wake_service.py'; Folder = "$root\tools\npu" } }
$services += @{ Name = 'vite-5173'; File = 'cmd.exe'; Arguments = '/c npm run dev'; Folder = "$root\frontend" }
if (Test-Path (Join-Path $JarvisConfigDir 'gateway\auth.json')) { $services += @{ Name = 'gateway-8443'; File = 'uv'; Arguments = 'run --no-sync python tools\gateway.py'; Folder = $root } }   # optional LAN/phone gateway, only after a password was set
$services = @($services | ForEach-Object { $_.Process = $null; [pscustomobject]$_ })

function Stop-JarvisHelper {
  # ends what an earlier supervisor left running (by port and by command line); the Jarvis server has its own tab and is not touched
  [CmdletBinding(SupportsShouldProcess = $true)]
  param()
  $ids = @()
  $ids += Get-NetTCPConnection -LocalPort $JarvisHelperPorts -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }
  $ids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $JarvisHelperProcessPattern -and $_.ProcessId -ne $PID } | ForEach-Object { $_.ProcessId }
  foreach ($i in ($ids | Sort-Object -Unique)) { if ($PSCmdlet.ShouldProcess("process $i", 'Stop')) { taskkill /PID $i /T /F 2>&1 | Out-Null } }
}
function Start-JarvisHelper {
  [CmdletBinding(SupportsShouldProcess = $true)]
  param($Service)
  if (-not $PSCmdlet.ShouldProcess($Service.Name, 'Start')) { return }
  $Service.Process = Start-Process -FilePath $Service.File -ArgumentList $Service.Arguments -WorkingDirectory $Service.Folder -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$log\$($Service.Name).out.log" -RedirectStandardError "$log\$($Service.Name).err.log"
  Write-Host ("{0,-12} started, PID {1}" -f $Service.Name, $Service.Process.Id)
}

Stop-JarvisHelper
foreach ($s in $services) { Start-JarvisHelper $s }
if ($WhatIfPreference) { exit 0 }
Write-Host "All started. Ctrl+C stops them all."
try {
  while ($true) {
    Start-Sleep 5
    foreach ($s in $services) {
      if ($s.Process.HasExited) { Write-Host "$($s.Name) stopped (exit $($s.Process.ExitCode)), restarting"; Start-JarvisHelper $s }
    }
  }
} finally {
  Stop-JarvisHelper
  Write-Host "All stopped."
}
