# IronMan J.A.R.V.I.S. installer for Windows 11 (Windows PowerShell 5, normal non-admin window).
# Run it from inside the cloned folder:
#   powershell -ExecutionPolicy Bypass -File .\install-jarvis.ps1
# It asks before every optional part (Hue, Tado, wake word, document search, fan monitor, web search key). Run it again any time; finished parts are skipped.
# Honest note: written from a working setup, NOT yet tested on a freshly wiped PC. Read the output of each step.
# The Windows installer (.exe) runs this script with -FromWizard: no questions, the answers come from the parameters below
# (the fan monitor's question is then Windows' own administrator prompt: answering No skips it).
# Exit codes: 0 = done, 1 = a required step failed, 10 = new programs were installed, start the script again in a fresh window.
param(
  [switch]$FromWizard,
  [switch]$WantHue, [string]$HueIp = '',
  [switch]$WantTado, [switch]$WantWake, [switch]$WantRag,
  [int]$ModelTier = 0,          # 1-3 = download that size ($JarvisModelTiers in tools\jarvis-common.ps1), 0 = none
  [string]$ModelId = '',        # an LM Studio model that is already installed
  [string]$OnlineModel = '',    # optional: Hugging Face repo found by tools\model-search.ps1 (tested after the download; on failure the choice above is used)
  [string]$WhisperModel = '',   # speech recognition size: tiny|base|small|medium|large-v3 (empty = recommended for this PC, see tools\voice-setup.ps1)
  [string]$TtsChoice = '',      # voice: kokoro|chatterbox (empty = kokoro; plain PowerShell use asks)
  [string]$VoiceClip = '',      # optional clip of your OWN voice for Chatterbox
  [string]$StatusFile = ''      # the wizard reads progress lines from this file
)
$ErrorActionPreference = 'Continue'
$Repo = $PSScriptRoot
# a clone inside C:\Windows (an administrator window starts in system32) breaks installs and cannot be written to normally
if ($Repo -like "$env:windir*") { Write-Host "ERROR: this folder is inside C:\Windows. Open a NORMAL (not administrator) PowerShell, run: cd $env:USERPROFILE ; then clone and run the script again." -ForegroundColor Red; exit 1 }
if (-not (Test-Path "$Repo\start-jarvis.ps1")) { Write-Host "Run this script from the IronMan-JARVIS folder." -ForegroundColor Red; exit 1 }
. (Join-Path $Repo 'tools\jarvis-common.ps1')
$Cfg  = $JarvisConfigDir
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$StepCount = 10   # the wizard's progress bar has 10 steps; the console shows the same numbers

# ---------- helpers ----------
function Get-Consent([string]$Question) { if ($FromWizard) { return $true }; return (Read-YesNo $Question) }
function Write-InstallStep([int]$Step, [string]$Text) {
  # the same step number and text for the console and for the wizard's progress bar
  Write-Host ""; Write-Host "[$Step/$StepCount] $Text" -ForegroundColor Cyan
  Write-WizardLine $StatusFile "STEP $Step|$Text"
}
function Exit-Install([string]$Reason) {
  # a required step failed: tell the wizard and end with exit code 1
  Write-Host "ERROR: $Reason" -ForegroundColor Red
  Write-WizardLine $StatusFile "FAIL|$Reason"
  if ($FromWizard) { try { Stop-Transcript | Out-Null } catch { Write-JarvisLog "install log not stopped: $($_.Exception.Message)" } }
  exit 1
}
function Test-Command([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function Write-CheckResult([string]$Name, [bool]$Ok, [string]$Hint) {
  if ($Ok) { Write-Host "  OK       $Name" -ForegroundColor Green }
  else     { Write-Host "  MISSING  $Name   ($Hint)" -ForegroundColor Yellow }
}
function Connect-HueBridge([string]$Ip) {
  # asks the Hue bridge for an app key (the round button on the bridge must have been pressed in the last 30 seconds)
  if ($Ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { Write-Host "That does not look like an IP address. Skipped Hue; run this script again." -ForegroundColor Yellow; return }
  [Environment]::SetEnvironmentVariable('HUE_BRIDGE_IP', $Ip, 'User')
  try { [System.IO.File]::WriteAllText("$Cfg\hue-ip.txt", $Ip, $Utf8) } catch { Write-JarvisLog "could not save the Hue address: $($_.Exception.Message)" }   # the installer wizard pre-fills the address from this after a reinstall
  if ($FromWizard -and (Test-Path "$Cfg\hue-key.txt")) { Write-Host "Hue key already saved."; return }
  if (-not $FromWizard) { Read-Host "Press the round button on top of the Hue bridge, THEN press Enter here" | Out-Null }
  try {
    $r = Invoke-RestMethod -Method Post -Uri "http://$Ip/api" -Body '{"devicetype":"ironman_jarvis#pc"}' -ContentType 'application/json'
    if ($r[0].success) { [System.IO.File]::WriteAllText("$Cfg\hue-key.txt", $r[0].success.username, $Utf8); Write-Host "Hue key saved (stays on this PC only)." -ForegroundColor Green }
    else { Write-Host "Bridge answered: $($r | ConvertTo-Json -Compress)  (did you press the button in time? run this script again)" -ForegroundColor Yellow }
  } catch { Write-Host "Could not reach the bridge at $Ip ($($_.Exception.Message)). Check the address and run this script again." -ForegroundColor Yellow }
}

# ---------- language model helpers (step 6) ----------
function Enable-ArmLmStudioEngine([string]$Lms) {
  # ARM PCs (Snapdragon): LM Studio picks the x86 Vulkan engine, which runs emulated and is very slow (3.7 tokens/s reading the prompt on a Surface).
  # Select its ARM64 CPU engine instead (the file below is what LM Studio's runtime setting writes). LM Studio must be closed while it is written.
  $bk = Join-Path $env:USERPROFILE '.lmstudio\extensions\backends'
  $vers = @(Get-ChildItem $bk -Directory -Filter 'llama.cpp-win-arm64-*' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name -replace '^llama\.cpp-win-arm64-', '' })
  if (-not $vers.Count) { return }
  # 2.54.0 is the one that worked on a Surface; the newest ARM engine failed its hardware survey there
  if ($vers -contains '2.54.0') { $ver = '2.54.0' } else { $ver = ($vers | Sort-Object { [version]$_ } | Select-Object -First 1) }
  try {
    Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep -Seconds 2
    $pf = Join-Path $env:USERPROFILE '.lmstudio\.internal\backend-preferences-v2.json'
    $o = [ordered]@{ formatDefaults = [ordered]@{}; versions = [ordered]@{} }
    if (Test-Path $pf) {
      try {
        $j = Get-Content $pf -Raw | ConvertFrom-Json
        if ($j.formatDefaults) { $j.formatDefaults.PSObject.Properties | ForEach-Object { $o.formatDefaults[$_.Name] = $_.Value } }
        if ($j.versions) { $j.versions.PSObject.Properties | ForEach-Object { $o.versions[$_.Name] = $_.Value } }
      } catch { Write-JarvisLog "LM Studio engine settings not readable, written fresh: $($_.Exception.Message)" }
    }
    $o.formatDefaults['gguf'] = 'llama.cpp-win-arm64'; $o.versions['llama.cpp-win-arm64'] = $ver
    [System.IO.File]::WriteAllText($pf, ($o | ConvertTo-Json -Depth 5), $Utf8)
    Write-Host "  ARM PC: LM Studio engine set to llama.cpp-win-arm64 $ver (much faster than the emulated x86 engine)." -ForegroundColor Green
  } catch { Write-Host "  Could not select the ARM engine: $($_.Exception.Message). In LM Studio: Runtime > GGUF > CPU llama.cpp (Windows ARM)." -ForegroundColor Yellow }
}
function Test-ModelToolCall([string]$Lms, [string]$Key) {
  # loads the model and asks one question that needs a tool; true when the model answers with the tool call
  & $Lms server start 2>&1 | Out-Null   # the chat test needs LM Studio's server (port 1234)
  if ($LASTEXITCODE -ne 0) { Write-JarvisLog "lms server start ended with code $LASTEXITCODE" }
  Start-Sleep -Seconds 3
  & $Lms load $Key -c 4096 -y 2>&1 | Out-Null
  $ok = $false
  try {
    $body = @{ model = $Key; temperature = 0; max_tokens = 200; tool_choice = 'auto'
      messages = @(@{ role = 'user'; content = 'What is the weather in Paris right now? Use the tool.' })
      tools = @(@{ type = 'function'; function = @{ name = 'get_weather'; description = 'Get the current weather of a city'; parameters = @{ type = 'object'; properties = @{ city = @{ type = 'string' } }; required = @('city') } } }) } | ConvertTo-Json -Depth 8
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$JarvisLmStudioPort/v1/chat/completions" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 240
    $ok = [bool]($r.choices[0].message.tool_calls -and "$($r.choices[0].message.tool_calls[0].function.name)" -eq 'get_weather')
  } catch { Write-Host "  Test error: $($_.Exception.Message)" -ForegroundColor Yellow }
  & $Lms unload --all 2>&1 | Out-Null
  return $ok
}
function Get-OnlineModel([string]$Lms, [string]$RepoId) {
  # downloads a newer model found online (Hugging Face) and tests it for tool calls; returns its LM Studio key, or $null (the normal choice is used then)
  $before = @(Get-LlmModel $Lms | ForEach-Object { $_.modelKey })
  Write-Host "  Downloading $RepoId (newest model found online, can take a while)..." -ForegroundColor Cyan
  Write-WizardLine $StatusFile "STEP 6|Downloading $RepoId (found online). This can take a very long time, please wait"
  # lms get reads "owner/name" as an LM Studio Hub name; a Hugging Face repo needs its full address
  $source = if ($RepoId -match '^https?://') { $RepoId } else { "https://huggingface.co/$RepoId" }
  & $Lms get $source --gguf -y 2>&1 | ForEach-Object { Write-Host "    $_" }
  $new = @(Get-LlmModel $Lms | Where-Object { $before -notcontains $_.modelKey } | Select-Object -First 1)
  if ($new.Count -eq 0) {
    Write-Host "  Could not confirm the download of $RepoId. Using the normal choice instead." -ForegroundColor Yellow
    Write-JarvisLog "online model $RepoId not downloaded (lms get $source)"
    return $null
  }
  $key = $new[0].modelKey
  Write-Host "  Testing $key (can it call tools?)..." -ForegroundColor Cyan
  Write-WizardLine $StatusFile "STEP 6|Testing $key (one quick tool-call test)"
  if (Test-ModelToolCall $Lms $key) { Write-Host "  $key passed the tool-call test." -ForegroundColor Green; return $key }
  Write-Host "  $key did not pass the tool-call test. Using the normal choice instead (the downloaded model stays in LM Studio)." -ForegroundColor Yellow
  Write-JarvisLog "online model $key failed the tool-call test"
  return $null
}
function Find-OnlineModel {
  # console only: asks whether to look online, runs tools\model-search.ps1 and asks again before using the result
  $ms = Join-Path $Repo 'tools\model-search.ps1'
  if (-not ((Read-Host "  Optional: look online for a newer model that fits your PC? (y/N)").Trim() -match '^[yY]')) { return '' }
  $tmpO = Join-Path $env:TEMP 'jarvis-models-online.txt'; Remove-Item $tmpO -Force -ErrorAction SilentlyContinue
  & $ms -Out $tmpO
  $bl = @(); if (Test-Path $tmpO) { $bl = @(Get-Content $tmpO | Where-Object { $_ -like 'BEST|*' }) }
  if ($bl.Count -eq 0) { Write-Host "  Nothing suitable found (or no internet). Continuing with the normal choice." -ForegroundColor Yellow; return '' }
  $bp = $bl[0] -split '\|'
  Write-Host ("   Found: {0}  (about {1} GB, added {2})" -f $bp[1], $bp[2], $bp[3])
  if ((Read-Host "  Use it? It is tested after the download and the normal choice is used if the test fails (y/N)").Trim() -match '^[yY]') { return $bp[1] }
  return ''
}
function Select-InstalledModel($Models) {
  # console only: picks one of the models already in LM Studio; returns its key, or $null for 'download a new one'
  Write-Host "  Models already in LM Studio:"
  for ($i = 0; $i -lt $Models.Count; $i++) { Write-Host ("   {0}) {1}  ({2:N1} GB)" -f ($i + 1), $Models[$i].modelKey, ($Models[$i].sizeBytes / 1GB)) }
  Write-Host "   0) download a new model instead"
  $n = (Read-Host "  Which model should Jarvis use? (number, Enter = 1)").Trim()
  if ($n -eq '') { $n = '1' }
  if ($n -match '^\d+$' -and [int]$n -ge 1 -and [int]$n -le $Models.Count) { return $Models[[int]$n - 1].modelKey }
  return $null
}
function Save-ModelTier([string]$Lms, [int]$WizardTier) {
  # recommends a size from the graphics memory, downloads the chosen tier and returns its LM Studio key (or $null).
  # WizardTier: the size chosen in the wizard (0 = none); in the console the user is asked.
  $hw = Get-HardwareInfo
  $rec = (Get-RecommendedModelTier $hw.Vram).Tier
  Write-Host ("  Your PC: GPU memory {0} GB, RAM {1} GB" -f $hw.Vram, $hw.Ram)
  foreach ($t in $JarvisModelTiers) {
    $mark = ''; if ($t.Tier -eq $rec) { $mark = '   <-- recommended for your PC' }
    Write-Host ("   {0}) about {1} GB  {2} - {3}{4}" -f $t.Tier, $t.Gb, $t.Id, $t.Note, $mark)
  }
  if ($FromWizard) { $answer = "$WizardTier" }
  else { $answer = (Read-Host "  Which one should I download? (1-$($JarvisModelTiers.Count), Enter = $rec, s = skip)").Trim(); if ($answer -eq '') { $answer = "$rec" } }
  $tier = $JarvisModelTiers | Where-Object { "$($_.Tier)" -eq $answer } | Select-Object -First 1
  if (-not $tier) { Write-Host "  Skipped. Download a model in LM Studio yourself, or run this script again."; return $null }
  $beforeKeys = @(Get-LlmModel $Lms | ForEach-Object { $_.modelKey })
  Write-Host "  Downloading $($tier.Id) (about $($tier.Gb) GB, can take a while)..." -ForegroundColor Cyan
  if ($FromWizard) {
    Write-WizardLine $StatusFile "STEP 6|Downloading $($tier.Id) (about $($tier.Gb) GB). This can take a very long time, please wait"
    $script:lastP = ''; $script:lastT = Get-Date
    & $Lms get $tier.Id -y 2>&1 | ForEach-Object {
      $s = "$_"; $pm = [regex]::Matches($s, '(\d{1,3}(?:\.\d+)?)\s?%')
      if ($pm.Count -gt 0) {
        $p = $pm[$pm.Count - 1].Groups[1].Value
        if ($p -ne $script:lastP -and ((Get-Date) - $script:lastT).TotalSeconds -ge 2) { Write-WizardLine $StatusFile "STEP 6|Downloading $($tier.Id): $p% (this can take a very long time, please wait)"; $script:lastP = $p; $script:lastT = Get-Date }
      } else { Write-Host "    $s" }
    }
  } else { & $Lms get $tier.Id -y }
  Write-Host "  lms get finished with code $LASTEXITCODE"
  # a Hugging Face id gets another model key in LM Studio: find the new one
  $newK = @(Get-LlmModel $Lms | Where-Object { $_.modelKey -eq $tier.Id -or $_.modelKey -eq $tier.Key -or ($beforeKeys -notcontains $_.modelKey) } | Select-Object -First 1)
  if ($newK.Count -gt 0) { return $newK[0].modelKey }
  Write-Host "  Could not confirm the download. Try by hand: lms get $($tier.Id)   (or search in the LM Studio app), then run this script again." -ForegroundColor Yellow
  return $null
}

New-Item -ItemType Directory -Force $Cfg | Out-Null
if ($FromWizard) { try { Start-Transcript -Path (Join-Path $Cfg 'install-log.txt') -Append | Out-Null } catch { Write-JarvisLog "install log not started: $($_.Exception.Message)" } }
Set-Location $Repo

# Wizard: pair with the Hue bridge FIRST (the button press is only valid for about 30 seconds)
if ($FromWizard -and $WantHue) { Write-InstallStep 1 "Philips Hue: pairing with the bridge"; Connect-HueBridge $HueIp }

# ---------- 1. programs ----------
Write-InstallStep 1 "Checking and installing programs (Git, uv, Node.js, Rust, Windows Terminal, LM Studio)"
$need = @()
if (-not (Test-Command git))    { $need += 'Git.Git' }
if (-not (Test-Command uv))     { $need += 'astral-sh.uv' }
if (-not (Test-Command node))   { $need += 'OpenJS.NodeJS' }
if (-not (Test-Command rustup)) { $need += 'Rustlang.Rustup' }
if (-not (Test-Command wt))     { $need += 'Microsoft.WindowsTerminal' }
if (-not (Get-LmStudioApp))     { $need += 'ElementLabs.LMStudio' }   # the APP must exist: a leftover ~\.lmstudio folder does not count
if ($need.Count -gt 0) {
  Write-Host "Missing programs: $($need -join ', ')" -ForegroundColor Yellow
  if (-not (Get-Consent "Install them now with winget?")) { Write-Host "Install them yourself, then run this script again."; exit 1 }
  foreach ($i in $need) {
    winget install --id $i -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Write-Host "winget could not install $i (code $LASTEXITCODE)." -ForegroundColor Yellow; Write-JarvisLog "winget install $i ended with code $LASTEXITCODE" }
  }
  if ($FromWizard) { Write-WizardLine $StatusFile 'RERUN|programs installed'; exit 10 }   # the wizard starts this script again in a fresh process
  Write-Host ""
  Write-Host "Close this PowerShell, open a NEW one (so the new programs are found) and run this script again." -ForegroundColor Yellow
  exit 10
}
Write-Host "All programs found." -ForegroundColor Green

# ---------- 2. options and settings file ----------
Write-InstallStep 2 "Writing your settings file"
if ($FromWizard) { $useHue = [bool]$WantHue; $useTado = [bool]$WantTado; $useWake = [bool]$WantWake }
else {
  $useHue  = Get-Consent "Use Philips Hue Smart Lights? (https://www.philips-hue.com/en-us/explore-hue)"
  $useTado = Get-Consent "Use Tado Smart Heating? (https://www.tado.com/en)"
  $useWake = Get-Consent "Set up the wake word 'Hey Jarvis' (openWakeWord, https://github.com/dscripka/openWakeWord ; own Python environment, a few minutes)?"
}
$cfgFile = "$Cfg\config.toml"
if (-not (Test-Path $cfgFile)) { Copy-Item "$Repo\config.example.toml" $cfgFile }
$c = [System.IO.File]::ReadAllText($cfgFile, [System.Text.Encoding]::UTF8)
$unused = @()
if (-not $useHue)  { $unused += 'hue_lights', 'hue_set', 'hue_light_list', 'hue_all_set' }
if (-not $useTado) { $unused += 'tado_heating' }
[System.IO.File]::WriteAllText($cfgFile, (Get-TomlWithoutListItem $c $unused), $Utf8)
Write-Host "Settings file: $cfgFile (analytics are OFF in it)" -ForegroundColor Green

# ---------- 3. Python and web packages ----------
Write-InstallStep 3 "Installing Python and web packages (a few minutes)"
rustup default stable
# a release tag like v1.0-installer breaks the version lookup (hatch-vcs); a fixed build version avoids that for every clone
$env:SETUPTOOLS_SCM_PRETEND_VERSION = "1.0.0"
uv sync --extra server --extra speech --extra scheduler --extra gpu-metrics --extra voice
if ($LASTEXITCODE -ne 0) { Exit-Install 'uv sync failed: the Python packages could not be installed. See the red text above. Nothing else was set up.' }
# 'uv sync' removes hand-added packages, so these are added afterwards. Always start things with 'uv run --no-sync'.
uv pip install maxminddb "python-tado>=1.0,<1.1" maturin pdfplumber psutil huggingface_hub
if ($LASTEXITCODE -ne 0) { Exit-Install 'uv pip install failed: the helper packages (maxminddb, python-tado, psutil ...) are missing.' }
# optional speed-up module (Rust). Not built on ARM PCs (Windows blocks the build there); Jarvis works the same without it.
if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { Write-Host "ARM PC: the optional Rust module is skipped." }
else {
  uv run --no-sync maturin develop -m rust/crates/openjarvis-python/Cargo.toml --release
  if ($LASTEXITCODE -ne 0) { Write-Host "Optional Rust module not built. Jarvis works the same without it." -ForegroundColor Yellow }
}
Set-Location "$Repo\frontend"; npm install; $npmCode = $LASTEXITCODE; Set-Location $Repo
if ($npmCode -ne 0) { Exit-Install "npm install failed (code $npmCode): the HUD web packages are missing." }

# ---------- 4. offline location database for the world map (public download, size-checked) ----------
Write-InstallStep 4 "Downloading the offline location database"
if (-not (Test-Path "$Repo\tools\dbip.mmdb")) {
  $gzFile = "$Repo\tools\dbip.mmdb.gz"
  $downloaded = $false
  foreach ($m in 0, 1, 2) {
    $ym = (Get-Date).AddMonths(-$m).ToString("yyyy-MM")
    try { Invoke-WebRequest "https://download.db-ip.com/free/dbip-city-lite-$ym.mmdb.gz" -OutFile $gzFile -UseBasicParsing; $downloaded = $true; Write-Host "downloaded $ym"; break }
    catch { Write-Host "not available: $ym" }
  }
  if ($downloaded) {
    $in  = [IO.File]::OpenRead($gzFile)
    $gz  = New-Object IO.Compression.GZipStream($in, [IO.Compression.CompressionMode]::Decompress)
    $out = [IO.File]::Create("$Repo\tools\dbip.mmdb")
    $gz.CopyTo($out); $out.Close(); $gz.Close(); $in.Close()
    Remove-Item $gzFile
    if ((Get-Item "$Repo\tools\dbip.mmdb").Length -lt 1MB) { Write-Host "Location database looks too small, deleting it." -ForegroundColor Yellow; Remove-Item "$Repo\tools\dbip.mmdb" }
  } else { Write-Host "Location database not downloaded. The world map works without it; run this script again later." -ForegroundColor Yellow }
}

# ---------- 5. wake word (optional) ----------
Write-InstallStep 5 "Wake word (optional)"
$NpuDir = "$Repo\tools\npu"
$wakeDone = "$NpuDir\.venv\jarvis-wake-ready.txt"   # written only when packages AND model files are complete, so a failed attempt is retried
if ($useWake -and -not (Test-WakeWordReady $NpuDir)) {
  $ProgressPreference = 'SilentlyContinue'
  Set-Location $NpuDir
  $vp = "$NpuDir\.venv\Scripts\python.exe"
  if (-not (Test-Path $vp)) { uv venv --python 3.12 .venv }
  uv pip install --python $vp sounddevice openwakeword==0.6.0
  $wakeOk = ($LASTEXITCODE -eq 0)
  if (-not $wakeOk) { Write-Host "Wake word packages FAILED to install. Wake word will not work (it is optional); run this script again to retry." -ForegroundColor Red }
  $md = "$NpuDir\.venv\Lib\site-packages\openwakeword\resources\models"
  New-Item -ItemType Directory -Force $md | Out-Null
  $base = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
  # each file must match its known SHA256 hash, otherwise it is deleted
  $hashes = @{
    "embedding_model.onnx" = "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f"
    "melspectrogram.onnx"  = "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f"
    "hey_jarvis_v0.1.onnx" = "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb"
  }
  foreach ($f in $hashes.Keys) {
    try {
      Invoke-WebRequest ($base + $f) -OutFile "$md\$f" -UseBasicParsing
      if ((Get-FileHash "$md\$f" -Algorithm SHA256).Hash.ToLower() -ne $hashes[$f]) { Remove-Item "$md\$f"; $wakeOk = $false; Write-Host "HASH MISMATCH for $f - file deleted" -ForegroundColor Red }
      else { Write-Host "downloaded and verified $f" }
    } catch { $wakeOk = $false; Write-Host "FAILED to download $f ($($_.Exception.Message))" -ForegroundColor Red }
  }
  if ($wakeOk) { [System.IO.File]::WriteAllText($wakeDone, 'wake word packages and models complete', $Utf8) }
  Set-Location $Repo
}

# ---------- 6. language model (LM Studio) ----------
Write-InstallStep 6 "Language model (LM Studio, a download can take a while)"
$lmsCmd = Get-LmsCommand
if (-not $lmsCmd -and $FromWizard) {
  # a fresh LM Studio creates its command line tool only after it has been started once
  $lmsApp = Get-LmStudioApp
  if ($lmsApp) {
    Write-Host "  Starting LM Studio once so it creates its command line tool (waiting up to 90 s)..." -ForegroundColor Cyan
    Start-Process $lmsApp
    $lmsFile = "$env:USERPROFILE\.lmstudio\bin\lms.exe"
    for ($w = 0; $w -lt 45 -and -not (Test-Path $lmsFile); $w++) { Start-Sleep -Seconds 2 }
    if (Test-Path $lmsFile) {
      $lmsCmd = $lmsFile
      & $lmsFile bootstrap 2>$null | Out-Null
      if ($LASTEXITCODE -ne 0) { Write-JarvisLog "lms bootstrap ended with code $LASTEXITCODE" }
    }
    Get-Process -Name 'LM Studio' -ErrorAction SilentlyContinue | Stop-Process -Force   # was started only to create lms.exe; start-jarvis.ps1 opens the real window later
  }
}
$chosen = $null
if (-not $lmsCmd) {
  Write-Host "  LM Studio command 'lms' not found. Open LM Studio once, run: lms bootstrap, open a NEW PowerShell and run this script again." -ForegroundColor Yellow
} else {
  if ((Get-HardwareInfo).Arm) { Enable-ArmLmStudioEngine $lmsCmd }
  # 1. a newer model found online (wizard: chosen on its page; console: asked here), tested for tool calls
  $online = ''
  if ($OnlineModel -match '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$') { $online = $OnlineModel }
  elseif (-not $FromWizard) { $online = Find-OnlineModel }
  if ($online) { $chosen = Get-OnlineModel $lmsCmd $online }
  # 2. a model that is already in LM Studio
  if (-not $chosen) {
    if ($FromWizard) { if (Test-ModelId $ModelId) { $chosen = $ModelId } }
    else {
      $installedModels = @(Get-LlmModel $lmsCmd)
      if ($installedModels.Count -gt 0) { $chosen = Select-InstalledModel $installedModels }
    }
  }
  # 3. download one of the three sizes
  if (-not $chosen) { $chosen = Save-ModelTier $lmsCmd $ModelTier }
  if ($chosen -and -not (Test-ModelId $chosen)) { Write-Host "  Model name has unexpected characters, not used: $chosen" -ForegroundColor Yellow; $chosen = $null }
  if ($chosen) {
    Write-Host "  Loading $chosen (context 8192)..." -ForegroundColor Cyan
    Write-WizardLine $StatusFile "STEP 6|Loading $chosen into memory (this can take a few minutes, please wait)"
    $parArg = @(); if (-not (Find-NvidiaSmi)) { $parArg = @('--parallel', '1') }   # processor only: one slot keeps the prompt cached
    & $lmsCmd load $chosen -c 8192 -y @parArg
    # remember the choice: start-jarvis.ps1 loads this model when none is loaded
    [System.IO.File]::WriteAllText((Join-Path $Cfg 'jarvis-model.txt'), $chosen, $Utf8)
    Write-Host "  Model saved: $chosen" -ForegroundColor Green
  }
}

# ---------- 7. document search: LM Studio plugin Big RAG (optional; https://lmstudio.ai/mindstudio/big-rag) ----------
Write-InstallStep 7 "Document search (optional)"
if ($FromWizard) { $ragAsked = [bool]$WantRag }
else { $ragAsked = ((Read-Host "Set up document search over your own files? Indexing is slow and the feature is fussy (y/N)").Trim() -match '^[yY]') }
if ($ragAsked -and -not $lmsCmd) {
  Write-Host "  LM Studio command 'lms' not found. Run lms bootstrap, open a NEW PowerShell and run this script again." -ForegroundColor Yellow
} elseif ($ragAsked) {
  # embedding model: needed by the plugin and by the oracle_search tool (small download)
  Write-Host "  Downloading the embedding model (nomic-embed-text, small)..." -ForegroundColor Cyan
  $embOk = $false
  foreach ($eid in 'nomic-ai/nomic-embed-text-v1.5', 'nomic-embed-text-v1.5', 'nomic-ai/nomic-embed-text-v1.5-GGUF') {
    & $lmsCmd get $eid -y 2>&1 | ForEach-Object { Write-Host "    $_" }
    if (@(Get-LlmModel $lmsCmd '' | Where-Object { "$($_.modelKey)" -match 'nomic-embed' }).Count -gt 0) { $embOk = $true; break }
  }
  if (-not $embOk) { Write-Host "  Embedding model not found after download. Get it later in LM Studio: search for nomic-embed-text-v1.5" -ForegroundColor Yellow }
  # plugin: first try the command line, then the lmstudio:// link
  $ragDir = Join-Path $env:USERPROFILE ".lmstudio\extensions\plugins\mindstudio\big-rag"
  if (-not (Test-Path $ragDir)) {
    Write-Host "  Installing plugin mindstudio/big-rag..." -ForegroundColor Cyan
    & $lmsCmd get mindstudio/big-rag -y
    if ($LASTEXITCODE -ne 0) { Write-JarvisLog "lms get mindstudio/big-rag ended with code $LASTEXITCODE" }
    Start-Sleep -Seconds 3
  }
  if (-not (Test-Path $ragDir)) {
    Write-Host "  Opening the plugin page in LM Studio..." -ForegroundColor Cyan
    Start-Process "lmstudio://plugin?owner=mindstudio&name=big-rag"
    if ($FromWizard) {
      Write-WizardLine $StatusFile "STEP 7|Document search: in LM Studio click install for Big RAG (waiting up to 2 minutes)"
      for ($w = 0; $w -lt 60 -and -not (Test-Path $ragDir); $w++) { Start-Sleep -Seconds 2 }
    } else { Read-Host "  In LM Studio click the install button for Big RAG, wait until it is done, THEN press Enter here" | Out-Null }
  }
  if (Test-Path $ragDir) { Write-Host "  Big RAG plugin found." -ForegroundColor Green }
  else { Write-Host "  Could not confirm the plugin folder (the path may differ). Check LM Studio > Plugins for Big RAG." -ForegroundColor Yellow }
  # documents folder (same default as the helper: JARVIS_DOC_ROOT or Documents\ORACLE)
  $ragDocs = $env:JARVIS_DOC_ROOT
  if (-not $ragDocs) { $ragDocs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ORACLE' }
  if (-not (Test-Path $ragDocs)) { New-Item -ItemType Directory -Path $ragDocs -Force | Out-Null }
  Write-Host "  Put your documents in: $ragDocs" -ForegroundColor Green
}

# ---------- 8. voice: speech recognition (Whisper size) and voice (Kokoro or Chatterbox), each tested after the download ----------
Write-InstallStep 8 "Voice models (a few minutes, much longer for the GPU voice)"
$llmGB = -1   # size of the language model sharing the graphics card: used for the recommendation
if ($chosen) { foreach ($lm in @(Get-LlmModel $lmsCmd)) { if ($lm.modelKey -eq $chosen) { $llmGB = [math]::Round($lm.sizeBytes / 1GB, 1) } } }
$vs = @{ Repo = $Repo; Whisper = $WhisperModel; Tts = $TtsChoice; VoiceClip = $VoiceClip; LlmGB = $llmGB; StatusFile = $StatusFile; StatusStep = 8 }
if (-not $FromWizard) { $vs.Ask = $true }
& "$Repo\tools\voice-setup.ps1" @vs
# the voice needs the small English language model of spaCy; install it now (pinned official release) so the first spoken answer does not download it
uv pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  spaCy language model not installed (code $LASTEXITCODE). The first spoken answer downloads it." -ForegroundColor Yellow }

# ---------- 9. Hue and Tado (optional) ----------
Write-InstallStep 9 "Philips Hue and Tado (optional)"
if ($useHue -and -not $FromWizard) {
  Write-Host "Philips Hue (https://www.philips-hue.com/en-us/explore-hue)"
  Connect-HueBridge (Read-Host "IP address of your Hue bridge (Hue app > Settings > Bridge)").Trim()
}
if ($useTado) {
  Write-Host "Tado login (https://www.tado.com/en): a link appears. Open it in your browser and approve the login."
  if (-not $FromWizard) { uv run --no-sync python tools\tado_login.py }
  elseif (Test-Path "$Cfg\tado-token.json") { Write-Host "Tado login already saved." }
  else {
    Write-WizardLine $StatusFile "STEP 9|Tado: approve the login in your browser (it opens by itself, waiting up to 2 minutes)"
    $tOut = Join-Path $env:TEMP 'tado-login-out.txt'; Remove-Item $tOut -ErrorAction SilentlyContinue
    $tErr = Join-Path $env:TEMP 'tado-login-err.txt'; Remove-Item $tErr -ErrorAction SilentlyContinue
    $tp = Start-Process -FilePath uv -ArgumentList 'run','--no-sync','python','-u','tools\tado_login.py' -WorkingDirectory $Repo -RedirectStandardOutput $tOut -RedirectStandardError $tErr -NoNewWindow -PassThru
    $opened = $false
    for ($w = 0; $w -lt 60 -and -not $tp.HasExited; $w++) {
      Start-Sleep -Seconds 2
      if ($opened) { continue }
      $all = ''; foreach ($f in $tOut, $tErr) { if (Test-Path $f) { $all += (Get-Content $f -Raw -ErrorAction SilentlyContinue) + "`n" } }
      $m = [regex]::Match($all, 'https://[^\s"''<>]*user_code[^\s"''<>]*')
      if (-not $m.Success) { $m = [regex]::Match($all, 'https://[^\s"''<>]*tado[^\s"''<>]*') }
      if ($m.Success) {
        $tu = $m.Value.TrimEnd('.', ',', ')'); Write-Host "  Tado login page: $tu"
        try { Start-Process $tu } catch { Start-Process cmd.exe -ArgumentList '/c','start','',$tu -WindowStyle Hidden }
        $opened = $true
      }
    }
    foreach ($f in $tOut, $tErr) { if (Test-Path $f) { Write-Host "  [tado output] $((Get-Content $f -Raw) -replace '\s+',' ')" } }   # kept in the install log for troubleshooting
    if (-not $tp.HasExited) { Stop-Process -Id $tp.Id -Force; Write-Host "Tado login timed out. Run tools\tado_login.py later (README)." -ForegroundColor Yellow }
  }
}

# ---------- 10. fan monitor (optional, needs administrator rights once), web search key, desktop shortcuts ----------
Write-InstallStep 10 "Fan monitor (Windows asks for administrator permission once)"
if (Get-ScheduledTask -TaskName $JarvisFanTaskName -ErrorAction SilentlyContinue) {
  Write-Host "  Fan monitor task already exists, skipped." -ForegroundColor Green
} elseif ($FromWizard -or (Get-Consent "Install the fan monitor for the HUD's fan panel (LibreHardwareMonitor, https://github.com/LibreHardwareMonitor/LibreHardwareMonitor; Windows asks for administrator permission)?")) {
  $fanRes = Join-Path $env:TEMP 'jarvis-fan-result.txt'
  Remove-Item $fanRes -ErrorAction SilentlyContinue
  try {
    Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -ResultFile "{1}"' -f (Join-Path $Repo 'tools\install-fan-monitor.ps1'), $fanRes)
    $fr = if (Test-Path $fanRes) { (Get-Content $fanRes -Raw).Trim() } else { 'FAIL|no answer' }
  } catch { $fr = 'FAIL|administrator permission was not given' }
  if ($fr -eq 'OK') { Write-Host "  Fan monitor installed and answering on port 8085." -ForegroundColor Green }
  elseif ($fr -eq 'NOWEB') { Write-Host "  Fan monitor installed, but its web server did not answer. Open LibreHardwareMonitor once (as administrator), Options > Remote Web Server > Run, turn Run On Windows Startup off." -ForegroundColor Yellow }
  else { Write-Host "  Fan monitor not installed ($($fr -replace '^FAIL\|', '')). The HUD works without it; see README, live fan speeds." -ForegroundColor Yellow }
} else { Write-Host "  Skipped. The HUD works without it." }

Write-InstallStep 10 "Web search key and desktop shortcut"
$key = $null
if ($FromWizard) { $key = $env:JARVIS_FIRECRAWL_KEY; $env:JARVIS_FIRECRAWL_KEY = $null }   # the wizard passes the key through its own process environment, never on a command line
else {
  $sec = Read-Host "Optional: paste your Firecrawl Web Data API key for web search (https://www.firecrawl.dev/, typed hidden, Enter to skip)" -AsSecureString
  $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
if ($key) { [Environment]::SetEnvironmentVariable("FIRECRAWL_API_KEY", $key, "User"); [Environment]::SetEnvironmentVariable("OPENJARVIS_WEB_SEARCH_ENGINE", "firecrawl", "User"); Write-Host "key saved as a user environment variable (never in a file)" }
$ws = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath('Desktop')
foreach ($sc in @(
    @{ Name = 'Jarvis';      Script = 'start-jarvis.ps1';       Icon = 'assets\jarvis.ico';      Args = '-ExecutionPolicy Bypass -WindowStyle Minimized -File' },
    @{ Name = 'Stop Jarvis'; Script = 'tools\stop-jarvis.ps1'; Icon = 'assets\jarvis-stop.ico'; Args = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File' })) {
  $s = $ws.CreateShortcut("$desk\$($sc.Name).lnk")
  $s.TargetPath = "powershell.exe"
  $s.Arguments = "$($sc.Args) `"$Repo\$($sc.Script)`""
  $s.WorkingDirectory = $Repo
  $ico = Join-Path $Repo $sc.Icon
  if (Test-Path $ico) { $s.IconLocation = $ico } else { $s.IconLocation = "powershell.exe,0" }   # J.A.R.V.I.S. icons for the desktop shortcuts
  $s.Save()
}

# ---------- final checks ----------
Write-Host ""; Write-Host "Checks:" -ForegroundColor Cyan
Write-CheckResult -Name "lms (LM Studio command)" -Ok ([bool](Get-LmsCommand)) -Hint "open LM Studio once, then run: lms bootstrap"
Write-CheckResult -Name "nvidia-smi" -Ok ([bool](Find-NvidiaSmi)) -Hint "no NVIDIA GPU: the GPU gauges will not work, the rest does"
Write-CheckResult -Name "settings file" -Ok (Test-Path $cfgFile) -Hint "rerun this script"
Write-CheckResult -Name "wake word" -Ok (Test-WakeWordReady $NpuDir) -Hint "optional"
Write-CheckResult -Name "language model" -Ok ([bool]$chosen) -Hint "choose one in step 6 (run this script again) or load one in LM Studio"
Write-Host ""
Write-Host "Still to do by hand:" -ForegroundColor Yellow
Write-Host " 1. Open LM Studio once, then in PowerShell run: lms bootstrap  (open a NEW PowerShell afterwards)"
Write-Host " 2. Language model: chosen in step 6 above. Skipped it, or want another? Run this script again."
Write-Host " 3. Double-click the Jarvis icon on your desktop. In your browser allow the microphone and remember the decision."
if ($ragAsked) {
  Write-Host " 4. Document search (Big RAG): in LM Studio open a chat, enable the Big RAG plugin and set: documents folder (see step 7),"
  Write-Host "    index folder (for example C:\AI\Big-RAG), embedding model nomic-ai/nomic-embed-text-v1.5-GGUF. Send one message to start indexing (slow)."
  Write-Host "    Then in the Jarvis folder run: uv run --no-sync python tools\ragcache.py   (see README, Document search)"
} else {
  Write-Host " 4. Optional document search: run this script again and answer y in step 7 (README, Document search)."
}
if (Test-Path $JarvisLogFile) { Write-Host "Notes about skipped or failed optional parts: $JarvisLogFile" }
Write-Host "Done." -ForegroundColor Green
Write-WizardLine $StatusFile 'DONE|finished'
if ($FromWizard) { try { Stop-Transcript | Out-Null } catch { Write-JarvisLog "install log not stopped: $($_.Exception.Message)" } }
exit 0
