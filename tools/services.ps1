# Jarvis services supervisor: runs the helper programs hidden in ONE terminal tab (started by start-jarvis.ps1).
# Services: helper 8765 (hwstats.py), HUD web server 5173 (Vite), wake word 8766 (only if set up), backup watcher (only if present).
# Logs: %USERPROFILE%\.openjarvis\logs (one .out.log and .err.log per service). Stop everything with tools\stop-jarvis.ps1.
$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $env:USERPROFILE '.openjarvis\logs'
New-Item -ItemType Directory -Force $log | Out-Null
# keep the console quiet: harmless library warnings are not shown (full errors still go to the log files)
$env:PYTHONWARNINGS = 'ignore'
$env:HF_HUB_VERBOSITY = 'error'
$svc = @()
if (Test-Path "$root\tools\backup-watch.ps1") { $svc += @{n='backup'; f='powershell.exe'; a="-NoProfile -ExecutionPolicy Bypass -File `"$root\tools\backup-watch.ps1`""; d=$root} }   # optional personal backup, not in the public repo
$svc += @{n='helper-8765'; f='uv'; a='run --no-sync python tools\hwstats.py'; d=$root}
$wakePy = "$root\tools\npu\.venv\Scripts\python.exe"
if (Test-Path $wakePy) { $svc += @{n='wake-8766'; f=$wakePy; a='wake_service.py'; d="$root\tools\npu"} }
$svc += @{n='vite-5173'; f='cmd.exe'; a='/c npm run dev'; d="$root\frontend"}
$run = @{}
function Stop-All {
  $ids = @()
  $ids += Get-NetTCPConnection -LocalPort 5173,8765,8766 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }
  $ids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'backup-watch\.ps1|hwstats\.py|wake_service\.py' -and $_.ProcessId -ne $PID } | ForEach-Object { $_.ProcessId }
  foreach ($i in ($ids | Sort-Object -Unique)) { taskkill /PID $i /T /F 2>&1 | Out-Null }
}
Stop-All
function Start-Svc($s) {
  $p = Start-Process -FilePath $s.f -ArgumentList $s.a -WorkingDirectory $s.d -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log\$($s.n).out.log" -RedirectStandardError "$log\$($s.n).err.log"
  $run[$s.n] = $p
  Write-Host ("{0,-12} started, PID {1}" -f $s.n, $p.Id)
}
foreach ($s in $svc) { Start-Svc $s }
Write-Host "All started. Ctrl+C stops them all."
try {
  while ($true) {
    Start-Sleep 5
    foreach ($s in $svc) {
      if ($run[$s.n].HasExited) { Write-Host "$($s.n) stopped (exit $($run[$s.n].ExitCode)), restarting"; Start-Svc $s }
    }
  }
} finally {
  Stop-All
  Write-Host "All stopped."
}
