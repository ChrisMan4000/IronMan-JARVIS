# Stop Jarvis: stops the supervisor, services, server and LM Studio. The browser is left open. The fan monitor (if installed) stops itself about 6 s later.
# Exit code 0 when everything stopped, 1 when a Jarvis port is still in use (the window then stays open so the message can be read).
param([switch]$KeepLmStudio)   # -KeepLmStudio: leave LM Studio and its model alone (used by the uninstallers)
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
Write-Host "Stopping Jarvis..."
# 1. supervisor first, so it cannot restart anything
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'services\.ps1' -and $_.ProcessId -ne $PID } | ForEach-Object { taskkill /PID $_.ProcessId /T /F 2>&1 | Out-Null }
# 2. by port (real python/node/uv children) and by command line (also closes the tabs)
$ids = @()
$ids += Get-NetTCPConnection -LocalPort $JarvisServicePorts -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess }
$ids += Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $JarvisProcessPattern -and $_.ProcessId -ne $PID } | ForEach-Object { $_.ProcessId }
foreach ($i in ($ids | Sort-Object -Unique)) { taskkill /PID $i /T /F 2>&1 | Out-Null }
# 2a. delete the stale server PID record (a reused PID blocks the next start)
Remove-Item (Join-Path $JarvisConfigDir 'server.pid'), (Join-Path $JarvisConfigDir 'server.pid.identity.json') -ErrorAction SilentlyContinue
# 2b. fan monitor: not stopped here on purpose (its own watcher closes LibreHardwareMonitor about 6 s after Jarvis is gone)
# 3. LM Studio: unload model, stop server, close app
$lms = Get-LmsCommand
if (-not $KeepLmStudio) {
  if ($lms) { & $lms unload --all 2>&1 | Out-Null; & $lms server stop 2>&1 | Out-Null }
  Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Stop-Process -Force
}
# 4. close only the Jarvis terminal window (by its tab title); other terminal windows are left alone
Import-JarvisWindowApi
$wins = @()
foreach ($title in "Jarvis Server $JarvisServerPort", 'Jarvis Services') { $h = [JarvisWin.User32]::FindWindow([NullString]::Value, $title); if ($h -ne [IntPtr]::Zero) { $wins += $h } }
# the window the launcher remembered (its title may have changed after the programs in it were killed)
$hf = Join-Path $JarvisConfigDir 'terminal-hwnd.txt'
if (Test-Path $hf) {
  foreach ($l in (Get-Content $hf -ErrorAction SilentlyContinue)) { if ($l -match '^\d+$') { $h = [IntPtr][int64]$l; if ([JarvisWin.User32]::IsWindow($h)) { $wins += $h } } }
  Remove-Item $hf -ErrorAction SilentlyContinue
}
# Windows Terminal asks "Close all tabs?" when a window with several tabs is closed. Everything in the Jarvis window is already stopped,
# so end that window's own Windows Terminal process (each window has its own process) if it has only this one window; other windows are never touched.
$wtWindows = @{}   # Windows Terminal process id -> number of its windows
$cur = [IntPtr]::Zero
do {
  # [NullString]::Value: a real null title (PowerShell would pass $null as an empty string, which matches no window)
  $cur = [JarvisWin.User32]::FindWindowEx([IntPtr]::Zero, $cur, 'CASCADIA_HOSTING_WINDOW_CLASS', [NullString]::Value)
  if ($cur -ne [IntPtr]::Zero) { $wp = [uint32]0; [void][JarvisWin.User32]::GetWindowThreadProcessId($cur, [ref]$wp); $wtWindows[[int]$wp] = 1 + [int]$wtWindows[[int]$wp] }
} while ($cur -ne [IntPtr]::Zero)
foreach ($h in ($wins | Sort-Object -Unique)) {
  $wp = [uint32]0; [void][JarvisWin.User32]::GetWindowThreadProcessId($h, [ref]$wp)
  $pn = (Get-Process -Id ([int]$wp) -ErrorAction SilentlyContinue).ProcessName
  if ($pn -eq 'WindowsTerminal' -and $wtWindows[[int]$wp] -eq 1) { taskkill /PID ([int]$wp) /F 2>&1 | Out-Null }
  else { [void][JarvisWin.User32]::PostMessage($h, 0x10, [IntPtr]::Zero, [IntPtr]::Zero) }   # 0x10 = WM_CLOSE
}
Start-Sleep 3
$check = @($JarvisServicePorts); if (-not $KeepLmStudio) { $check += $JarvisLmStudioPort }
$left = @(Get-NetTCPConnection -LocalPort $check -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.LocalPort } | Sort-Object -Unique)
if ($left.Count -eq 0) { Write-Host "Jarvis stopped."; Start-Sleep 3; exit 0 }   # exit code 0: Windows Terminal closes the window by itself
Write-Host ("Still listening: " + ($left -join ', ') + ". Close the programs on these ports or restart the PC.") -ForegroundColor Yellow
Start-Sleep 10
exit 1
