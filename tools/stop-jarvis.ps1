# Stop Jarvis: stops the supervisor, services, server and LM Studio. The browser is left open. The fan monitor (if installed) stops itself about 6 s later.
param([switch]$KeepLmStudio)   # -KeepLmStudio: leave LM Studio and its model alone (used by the uninstaller)
Write-Host "Stopping Jarvis..."
$pat = 'services\.ps1|backup-watch\.ps1|hwstats\.py|wake_service\.py|jarvis serve'
# 1. supervisor first, so it cannot restart anything
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'services\.ps1' -and $_.ProcessId -ne $PID } | ForEach-Object { taskkill /PID $_.ProcessId /T /F 2>&1 | Out-Null }
# 2. by port (real python/node/uv children) and by command line (also closes the tabs)
$ids = @()
$ids += Get-NetTCPConnection -LocalPort 5173,8000,8765,8766 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }
$ids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pat -and $_.ProcessId -ne $PID } | ForEach-Object { $_.ProcessId }
foreach ($i in ($ids | Sort-Object -Unique)) { taskkill /PID $i /T /F 2>&1 | Out-Null }
# 2a. delete the stale server PID record (a reused PID blocks the next start)
Remove-Item "$env:USERPROFILE\.openjarvis\server.pid","$env:USERPROFILE\.openjarvis\server.pid.identity.json" -ErrorAction SilentlyContinue
# 2b. fan monitor: not stopped here on purpose (its own watcher closes LibreHardwareMonitor about 6 s after Jarvis is gone)
# 3. LM Studio: unload model, stop server, close app
$lmsCmd = if (Get-Command lms -ErrorAction SilentlyContinue) { 'lms' } elseif (Test-Path "$env:USERPROFILE\.lmstudio\bin\lms.exe") { "$env:USERPROFILE\.lmstudio\bin\lms.exe" } else { $null }
if (-not $KeepLmStudio) {
  if ($lmsCmd) { & $lmsCmd unload --all 2>&1 | Out-Null; & $lmsCmd server stop 2>&1 | Out-Null }
  Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Stop-Process -Force
}
# 4. close only the Jarvis terminal window (by its tab title); other terminal windows are left alone
Add-Type -Namespace W2 -Name S -MemberDefinition '[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string c, string t); [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);'
foreach ($tt in 'Jarvis Server 8000','Jarvis Services') { $h = [W2.S]::FindWindow([NullString]::Value, $tt); if ($h -ne [IntPtr]::Zero) { [void][W2.S]::PostMessage($h, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) } }
Start-Sleep 3
$left = @(Get-NetTCPConnection -LocalPort 5173,8000,8765,8766,1234 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.LocalPort })
if ($left.Count -eq 0) { Write-Host "Jarvis stopped." } else { Write-Host ("Still listening: " + ($left -join ',')) }
Start-Sleep 3
