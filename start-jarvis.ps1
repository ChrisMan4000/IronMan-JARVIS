# start-jarvis.ps1 - starts everything for Jarvis in order:
# LM Studio -> model -> Backup Watcher, helper (8765), wake word (8766), server (8000) -> HUD (5173) -> browser.
# Reviewed 2026-10-14: the model id is checked before it is put into a command line.
$root = $PSScriptRoot   # the folder this script lives in

# Wait-For: asks a web address every 2 seconds until it answers (or the time runs out)

function Wait-For($url, $name, $timeoutSec = 180) {
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

# --- Step 1: LM Studio must be running
Write-Host "Checking LM Studio..." -ForegroundColor Cyan
function Test-Lms { try { Invoke-WebRequest "http://localhost:1234/v1/models" -TimeoutSec 3 -UseBasicParsing | Out-Null; return $true } catch { return $false } }
function Get-Loaded {
  try {
    $d = (Invoke-RestMethod "http://localhost:1234/api/v0/models" -TimeoutSec 5).data
    return @($d | Where-Object { $_.state -eq "loaded" -and ($_.type -eq "llm" -or $_.type -eq "vlm") } | ForEach-Object { $_.id })
  } catch { return @() }
}
# Open the LM Studio window (visible, not hidden in the tray). LM Studio is single-instance: if it is already open this just brings it to the front.
$lmsExe = @("$env:LOCALAPPDATA\Programs\LM Studio\LM Studio.exe", "$env:ProgramFiles\LM Studio\LM Studio.exe", "${env:ProgramFiles(x86)}\LM Studio\LM Studio.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($lmsExe) { Write-Host "Opening LM Studio: $lmsExe"; Start-Process $lmsExe -WindowStyle Normal; Start-Sleep -Seconds 5 } else { Write-Host "The LM Studio app was not found (only its hidden server can start). Run the Jarvis installer again to install LM Studio." -ForegroundColor Yellow }
if (-not (Test-Lms)) {
  Write-Host "LM Studio server is not running - starting it..." -ForegroundColor Yellow
  lms server start
}
if (-not (Wait-For "http://localhost:1234/v1/models" "LM Studio")) { Read-Host "Press Enter to close"; exit }
# --- Step 2: make sure one model is loaded, with the context size saved by the HUD
$ReloadOnContextMismatch = $true
function Get-SavedCtx($id) {
  $c = 8192
  try {
    $s = Get-Content "$env:USERPROFILE\.openjarvis\hud-model-settings.json" -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
    $pr = $s.PSObject.Properties[$id]
    if ($pr -and $pr.Value.context) { $c = [int]$pr.Value.context }
  } catch {}
  return $c
}
$info = $null
try {
  $info = (Invoke-RestMethod "http://localhost:1234/api/v0/models" -TimeoutSec 5).data |
    Where-Object { $_.state -eq "loaded" -and ($_.type -eq "llm" -or $_.type -eq "vlm") } | Select-Object -First 1
} catch {}
if ($info) {
  $model = $info.id
  $want = Get-SavedCtx $model
  if ($ReloadOnContextMismatch -and $info.loaded_context_length -and [int]$info.loaded_context_length -ne $want) {
    Write-Host "Model $model is loaded with context $($info.loaded_context_length), saved context is $want - reloading..." -ForegroundColor Yellow
    lms unload --all
    lms load $model -c $want -y
  } else {
    Write-Host "Model already loaded: $model (context $($info.loaded_context_length))" -ForegroundColor Green
  }
} else {
  $model = "google/gemma-4-26b-a4b-qat"
  $savedModelFile = Join-Path $env:USERPROFILE ".openjarvis\jarvis-model.txt"   # model chosen by install-jarvis.ps1
  if (Test-Path $savedModelFile) { $sm = (Get-Content $savedModelFile -Raw).Trim(); if ($sm -match '^[A-Za-z0-9._:/@+-]+$') { $model = $sm } }
  # try the saved/default model first, then every other LLM in LM Studio, until one really loads (some models cannot load on some PCs)
  $cands = @($model)
  try {
    $arr = ConvertFrom-Json ((lms ls --json 2>$null) -join "`n")
    foreach ($m in $arr) { if ($m.type -eq 'llm' -and $m.modelKey -and ($cands -notcontains $m.modelKey) -and $m.modelKey -match '^[A-Za-z0-9._:/@+-]+$') { $cands += $m.modelKey } }
  } catch {}
  $loadedOk = $false
  foreach ($c in $cands) {
    $want = Get-SavedCtx $c
    Write-Host "No model loaded - loading $c with context $want..." -ForegroundColor Yellow
    lms load $c -c $want -y
    $chk = $null
    try { $chk = (Invoke-RestMethod "http://localhost:1234/api/v0/models" -TimeoutSec 5).data | Where-Object { $_.id -eq $c -and $_.state -eq "loaded" } | Select-Object -First 1 } catch {}
    if ($chk) { $model = $c; $loadedOk = $true; break }
    Write-Host "Could not load $c - trying the next model..." -ForegroundColor Yellow
  }
  if (-not $loadedOk) {
    Write-Host "No language model could be loaded. Open LM Studio, download a model that runs on your PC, then start Jarvis again." -ForegroundColor Red
    Read-Host "Press Enter to close"; exit
  }
}
# Safety: the model id ends up inside a command line, so only plain characters are allowed
if ($model -notmatch '^[A-Za-z0-9._:/@+-]+$') {
  Write-Host "Model name has unexpected characters, refusing to start: $model" -ForegroundColor Red
  Read-Host "Press Enter to close"; exit
}

# --- Step 2b: early warm-up straight to LM Studio (runs in the background)
Start-Job -ArgumentList $model -ScriptBlock { param($m) try { $b = @{model=$m; max_tokens=1; messages=@(@{role='user'; content='Hi'})} | ConvertTo-Json -Depth 5; Invoke-RestMethod -Method Post -Uri http://localhost:1234/v1/chat/completions -Body $b -ContentType 'application/json' -TimeoutSec 300 | Out-Null } catch {} } | Out-Null
# --- Step 3: start the helper programs and the Jarvis server, each in its own terminal tab
$env:PYTHONWARNINGS = 'ignore'; $env:HF_HUB_VERBOSITY = 'error'   # keeps harmless library warnings out of the terminal windows (inherited by the tabs; no semicolons in the wt command, wt would split it)
# optional fan monitor: only runs if tools\setup-fan-monitor.ps1 was used (starts LibreHardwareMonitor hidden, closes it again after Jarvis stops)
Stop-ScheduledTask -TaskName "LibreHardwareMonitor Hidden" -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Start-ScheduledTask -TaskName "LibreHardwareMonitor Hidden" -ErrorAction SilentlyContinue   # stop first: an old watcher would ignore the start
# one tab "Jarvis Services" runs the helper (8765), the HUD web server (5173), the wake word (8766, if set up) and the backup watcher (if present); see tools\services.ps1
Start-Process wt -WindowStyle Minimized -ArgumentList "-w jarvis new-tab -d `"$root`" --title `"Jarvis Services`" --suppressApplicationTitle powershell -NoExit -ExecutionPolicy Bypass -File `"$root\tools\services.ps1`""
Start-Sleep -Seconds 2
Start-Process wt -ArgumentList "-w jarvis new-tab -d `"$root`" --title `"Jarvis Server 8000`" --suppressApplicationTitle powershell -NoExit -Command `"uv run --no-sync jarvis serve --engine lmstudio --model '$model' --port 8000 --agent orchestrator`""
if (-not (Wait-For "http://127.0.0.1:8000/health" "Jarvis")) { Read-Host "Press Enter to close"; exit }

# --- Step 4: wait for the HUD web server (started by the Services tab)
Add-Type -Namespace W -Name S -MemberDefinition '[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string c, string t); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);'
if (-not (Wait-For "http://localhost:5173/" "Frontend")) { Read-Host "Press Enter to close"; exit }

# opens the default browser

Start-Process "http://localhost:5173/"
Start-Sleep -Seconds 2
Start-Process "http://localhost:5173/hud.html"

# --- Step 5: minimise the terminal windows
Start-Sleep -Seconds 3
foreach ($i in 1..10) { $done = $false; foreach ($ti in 'Jarvis Services','Jarvis Server 8000') { $h = [W.S]::FindWindow('CASCADIA_HOSTING_WINDOW_CLASS', $ti); if ($h -ne [IntPtr]::Zero) { [void][W.S]::ShowWindow($h, 6); $done = $true } }; if ($done) { break }; Start-Sleep -Seconds 1 }
Write-Host "All done." -ForegroundColor Green
# --- Step 6: warm-up (first request is slow): runs hidden in the background, so this window can close right away
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$root\tools\warmup.ps1`" -Model `"$model`""
Start-Sleep -Seconds 2
exit
