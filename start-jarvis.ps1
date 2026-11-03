# start-jarvis.ps1 - starts everything for Jarvis in order:
# LM Studio -> model -> Backup Watcher, helper (8765), wake word (8766), server (8000) -> HUD (5173) -> browser.
# Every model id is checked with Test-ModelId before it is put into a command line (lms load, jarvis serve).
# -KeepContext: use an already loaded model as it is, even when its context size differs from the one saved in the HUD.
param([switch]$KeepContext)
$root = $PSScriptRoot   # the folder this script lives in
. (Join-Path $root 'tools\jarvis-common.ps1')
# Settings the installer saved as Windows user variables (web search key, Hue address ...) are only seen by programs started AFTER they were set;
# a desktop icon starts this script from Explorer, which still has the old list. Read them again so the server always gets them.
foreach ($n in $JarvisUserEnvVars) { $v = [Environment]::GetEnvironmentVariable($n, 'User'); if ($v) { Set-Item -Path "Env:$n" -Value $v } }

function Wait-For($url, $name, $timeoutSec = 180) {
  # asks a web address every 2 seconds until it answers (or the time runs out)
  Write-Host "Waiting for $name..." -ForegroundColor Cyan
  $end = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $end) {
    try {
      Invoke-WebRequest $url -TimeoutSec 3 -UseBasicParsing | Out-Null
      Write-Host "$name is up." -ForegroundColor Green
      return $true
    } catch { Start-Sleep -Seconds 2 }
  }
  Write-Host "$name did not start in time." -ForegroundColor Red
  return $false
}
function Exit-WithMessage([string]$Text) {
  # a step failed: show why and keep the window open, exit code 1
  Write-Host $Text -ForegroundColor Red
  Read-Host "Press Enter to close" | Out-Null
  exit 1
}
function Get-LoadedModel {
  # the language model LM Studio has loaded right now (id, loaded_context_length ...), or $null
  try {
    $d = (Invoke-RestMethod "http://localhost:$JarvisLmStudioPort/api/v0/models" -TimeoutSec 5).data
    return ($d | Where-Object { $_.state -eq 'loaded' -and ($_.type -eq 'llm' -or $_.type -eq 'vlm') } | Select-Object -First 1)
  } catch { Write-JarvisLog "LM Studio model list not readable: $($_.Exception.Message)"; return $null }
}
function Get-SavedContext([string]$Id) {
  # context size the HUD saved for this model (default 8192)
  $c = 8192
  $f = Join-Path $JarvisConfigDir 'hud-model-settings.json'
  if (Test-Path $f) {
    try {
      $pr = (Get-Content $f -Raw | ConvertFrom-Json).PSObject.Properties[$Id]
      if ($pr -and $pr.Value.context) { $c = [int]$pr.Value.context }
    } catch { Write-JarvisLog "saved model settings not readable ($f): $($_.Exception.Message)" }
  }
  return $c
}

$lms = Get-LmsCommand
# PCs without an NVIDIA card (processor only): one slot, so the long Jarvis prompt stays cached between questions (with 4 slots it was read again from scratch every time, minutes per answer on a Surface)
$lmsPar = @(); if (-not (Find-NvidiaSmi)) { $lmsPar = @('--parallel', '1') }

# --- Step 1: LM Studio must be running
Write-Host "Checking LM Studio..." -ForegroundColor Cyan
# Open the LM Studio window (visible, not hidden in the tray). LM Studio is single-instance: if it is already open this just brings it to the front.
$lmsApp = Get-LmStudioApp
if ($lmsApp) {
  Write-Host "Opening LM Studio: $lmsApp"
  # an LM Studio that was started hidden (tray only) is closed first, otherwise starting it again shows no window
  $withWindow = @(Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 })
  if (-not $withWindow.Count -and (Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue)) { Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep -Seconds 3 }
  Start-Process $lmsApp -WindowStyle Normal; Start-Sleep -Seconds 5
  # still no window (LM Studio sometimes starts in the tray when the launcher itself is minimized): start it once more, a second start shows the window
  if (-not @(Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }).Count) { Start-Process $lmsApp -WindowStyle Normal; Start-Sleep -Seconds 3 }
} else { Write-Host "The LM Studio app was not found (only its hidden server can start). Run the Jarvis installer again to install LM Studio." -ForegroundColor Yellow }
$lmsUrl = "http://localhost:$JarvisLmStudioPort/v1/models"
try { Invoke-WebRequest $lmsUrl -TimeoutSec 3 -UseBasicParsing | Out-Null }
catch {
  if (-not $lms) { Exit-WithMessage "LM Studio's command line tool 'lms' was not found. Open LM Studio once, run: lms bootstrap, then start Jarvis again." }
  Write-Host "LM Studio server is not running - starting it..." -ForegroundColor Yellow
  & $lms server start
}
if (-not (Wait-For $lmsUrl "LM Studio")) { Exit-WithMessage "LM Studio did not answer on port $JarvisLmStudioPort." }

# --- Step 2: make sure one model is loaded, with the context size saved by the HUD
$info = Get-LoadedModel
if ($info -and -not (Test-ModelId $info.id)) { Exit-WithMessage "The loaded model's name has unexpected characters, refusing to use it: $($info.id)" }
if ($info) {
  $model = $info.id
  $want = Get-SavedContext $model
  if (-not $KeepContext -and $lms -and $info.loaded_context_length -and [int]$info.loaded_context_length -ne $want) {
    Write-Host "Model $model is loaded with context $($info.loaded_context_length), saved context is $want - reloading..." -ForegroundColor Yellow
    & $lms unload --all
    & $lms load $model -c $want -y @lmsPar
  } else {
    Write-Host "Model already loaded: $model (context $($info.loaded_context_length))" -ForegroundColor Green
  }
} else {
  if (-not $lms) { Exit-WithMessage "No model is loaded and LM Studio's command line tool 'lms' was not found. Load a model in LM Studio, then start Jarvis again." }
  # try the model chosen by install-jarvis.ps1 (else the default), then every other LLM in LM Studio, until one really loads (some models cannot load on some PCs)
  $first = ($JarvisModelTiers | Select-Object -Last 1).Id
  $savedModelFile = Join-Path $JarvisConfigDir 'jarvis-model.txt'
  if (Test-Path $savedModelFile) { $sm = (Get-Content $savedModelFile -Raw).Trim(); if (Test-ModelId $sm) { $first = $sm } }
  $cands = @($first) + @(Get-LlmModel $lms | ForEach-Object { $_.modelKey } | Where-Object { $_ -ne $first -and (Test-ModelId $_) })
  $model = $null
  foreach ($c in $cands) {
    $want = Get-SavedContext $c
    Write-Host "No model loaded - loading $c with context $want..." -ForegroundColor Yellow
    & $lms load $c -c $want -y @lmsPar
    $now = Get-LoadedModel
    if ($now -and $now.id -eq $c) { $model = $c; break }
    Write-Host "Could not load $c - trying the next model..." -ForegroundColor Yellow
  }
  if (-not $model) { Exit-WithMessage "No language model could be loaded. Open LM Studio, download a model that runs on your PC, then start Jarvis again." }
}

# --- Step 2b: early warm-up straight to LM Studio (runs in the background)
$warmUrl = "http://localhost:$JarvisLmStudioPort/v1/chat/completions"
Start-Job -ScriptBlock {
  $b = @{ model = $using:model; max_tokens = 1; messages = @(@{ role = 'user'; content = 'Hi' }) } | ConvertTo-Json -Depth 5
  try { Invoke-RestMethod -Method Post -Uri $using:warmUrl -Body $b -ContentType 'application/json' -TimeoutSec 300 | Out-Null }
  catch { 'warm-up failed: ' + $_.Exception.Message }   # the job's output is never read: the first answer is just slower
} | Out-Null

# --- Step 3: start the helper programs and the Jarvis server, each in its own terminal tab
$env:PYTHONWARNINGS = 'ignore'; $env:HF_HUB_VERBOSITY = 'error'   # keeps harmless library warnings out of the terminal windows (inherited by the tabs; no semicolons in the wt command, wt would split it)
# optional fan monitor: only runs if tools\setup-fan-monitor.ps1 was used (starts LibreHardwareMonitor hidden, closes it again after Jarvis stops)
Stop-ScheduledTask -TaskName $JarvisFanTaskName -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Start-ScheduledTask -TaskName $JarvisFanTaskName -ErrorAction SilentlyContinue   # stop first: an old watcher would ignore the start
# one tab "Jarvis Services" runs the helper (8765), the HUD web server (5173), the wake word (8766, if set up) and the backup watcher (if present); see tools\services.ps1
Start-Process wt -WindowStyle Minimized -ArgumentList "-w jarvis new-tab -d `"$root`" --title `"Jarvis Services`" --suppressApplicationTitle powershell -NoExit -ExecutionPolicy Bypass -File `"$root\tools\services.ps1`""
Start-Sleep -Seconds 2
Start-Process wt -ArgumentList "-w jarvis new-tab -d `"$root`" --title `"Jarvis Server $JarvisServerPort`" --suppressApplicationTitle powershell -NoExit -Command `"uv run --no-sync jarvis serve --engine lmstudio --model '$model' --port $JarvisServerPort --agent orchestrator`""
if (-not (Wait-For "http://127.0.0.1:$JarvisServerPort/health" "Jarvis")) { Exit-WithMessage "The Jarvis server did not start. Look at the 'Jarvis Server' terminal tab for the error." }

# --- Step 4: wait for the HUD web server (started by the Services tab), then open the browser
if (-not (Wait-For "http://localhost:5173/" "Frontend")) { Exit-WithMessage "The HUD web server did not start. Look at %USERPROFILE%\.openjarvis\logs\vite-5173.err.log." }
Start-Process "http://localhost:5173/"
Start-Sleep -Seconds 2
Start-Process "http://localhost:5173/hud.html"

# --- Step 5: minimise the terminal windows and remember them, so Stop Jarvis can close them even when their title has changed
Import-JarvisWindowApi
Start-Sleep -Seconds 3
$handles = @()
foreach ($i in 1..10) {
  foreach ($title in 'Jarvis Services', "Jarvis Server $JarvisServerPort") {
    $h = [JarvisWin.User32]::FindWindow('CASCADIA_HOSTING_WINDOW_CLASS', $title)
    if ($h -ne [IntPtr]::Zero) { [void][JarvisWin.User32]::ShowWindow($h, 6); $handles += [string]$h.ToInt64() }   # 6 = minimise
  }
  if ($handles.Count) { break }
  Start-Sleep -Seconds 1
}
try { [System.IO.File]::WriteAllLines((Join-Path $JarvisConfigDir 'terminal-hwnd.txt'), [string[]]@($handles | Select-Object -Unique)) } catch { Write-JarvisLog "terminal window list not saved: $($_.Exception.Message)" }
Write-Host "All done." -ForegroundColor Green
# --- Step 6: warm-up (first request is slow): runs hidden in the background, so this window can close right away
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$root\tools\warmup.ps1`" -Model `"$model`""
Start-Sleep -Seconds 2
exit 0
