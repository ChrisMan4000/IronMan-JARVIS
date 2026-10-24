# IronMan J.A.R.V.I.S. installer for Windows 11 (Windows PowerShell 5, normal non-admin window).
# Run it from inside the cloned folder:
#   powershell -ExecutionPolicy Bypass -File .\install-jarvis.ps1
# It asks before every optional part (Hue, Tado, wake word, web search key). Run it again any time; finished parts are skipped.
# Honest note: written from a working setup, NOT yet tested on a freshly wiped PC. Read the output of each step.
$ErrorActionPreference = 'Continue'
$Repo = $PSScriptRoot
$Cfg  = Join-Path $env:USERPROFILE '.openjarvis'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
function Ask($q) { $a = Read-Host "$q (y/n)"; return ($a -match '^\s*y') }
function Have($c) { return [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Chk($name, $ok, $hint) {
  if ($ok) { Write-Host "  OK       $name" -ForegroundColor Green }
  else     { Write-Host "  MISSING  $name   ($hint)" -ForegroundColor Yellow }
}
Set-Location $Repo
if (-not (Test-Path "$Repo\start-jarvis.ps1")) { Write-Host "Run this script from the IronMan-JARVIS folder." -ForegroundColor Red; exit }

# ---------- 1. programs ----------
Write-Host "Step 1: programs" -ForegroundColor Cyan
$need = @()
if (-not (Have git))    { $need += 'Git.Git' }
if (-not (Have uv))     { $need += 'astral-sh.uv' }
if (-not (Have node))   { $need += 'OpenJS.NodeJS' }
if (-not (Have rustup)) { $need += 'Rustlang.Rustup' }
if (-not (Have wt))     { $need += 'Microsoft.WindowsTerminal' }
$lmsOk = (Have lms) -or (Test-Path "$env:USERPROFILE\.lmstudio\bin\lms.exe")
if (-not $lmsOk)        { $need += 'ElementLabs.LMStudio' }
if ($need.Count -gt 0) {
  Write-Host "Missing programs: $($need -join ', ')" -ForegroundColor Yellow
  if (Ask "Install them now with winget?") {
    foreach ($i in $need) { winget install --id $i -e --accept-package-agreements --accept-source-agreements }
    Write-Host ""
    Write-Host "Close this PowerShell, open a NEW one (so the new programs are found) and run this script again." -ForegroundColor Yellow
    exit
  } else { Write-Host "Install them yourself, then run this script again."; exit }
}
Write-Host "All programs found." -ForegroundColor Green

# ---------- 2. options ----------
Write-Host ""; Write-Host "Step 2: options" -ForegroundColor Cyan
$useHue  = Ask "Use Philips Hue lights?"
$useTado = Ask "Use Tado heating?"
$useWake = Ask "Set up the wake word 'Hey Jarvis' (own Python environment, a few minutes)?"

# ---------- 3. settings file ----------
New-Item -ItemType Directory -Force $Cfg | Out-Null
$cfgFile = "$Cfg\config.toml"
if (-not (Test-Path $cfgFile)) { Copy-Item "$Repo\config.example.toml" $cfgFile }
$c = [System.IO.File]::ReadAllText($cfgFile, [System.Text.Encoding]::UTF8)
if (-not $useHue)  { $c = [regex]::Replace($c, '\s*"hue_(lights|set|light_list|all_set)",?', '') }
if (-not $useTado) { $c = [regex]::Replace($c, '\s*"tado_heating",?', '') }
$c = [regex]::Replace($c, ',(\s*)\]', '$1]')
[System.IO.File]::WriteAllText($cfgFile, $c, $Utf8)
Write-Host "Settings file: $cfgFile (analytics are OFF in it)" -ForegroundColor Green

# ---------- 4. Python and web packages ----------
Write-Host ""; Write-Host "Step 4: packages (a few minutes)" -ForegroundColor Cyan
rustup default stable
uv sync --extra server --extra speech --extra scheduler --extra gpu-metrics --extra voice
# 'uv sync' removes hand-added packages, so these are added afterwards. Always start things with 'uv run --no-sync'.
uv pip install maxminddb python-tado maturin pdfplumber psutil
uv run --no-sync maturin develop -m rust/crates/openjarvis-python/Cargo.toml --release
if ($LASTEXITCODE -ne 0) { Write-Host "Rust module build failed. Jarvis still starts (you only get a 'No module named openjarvis_rust' warning)." -ForegroundColor Yellow }
Set-Location "$Repo\frontend"; npm install; Set-Location $Repo

# ---------- 5. offline location database for the world map (public download, size-checked) ----------
if (-not (Test-Path "$Repo\tools\dbip.mmdb")) {
  $ok = $false
  foreach ($m in 0, 1, 2) {
    $ym = (Get-Date).AddMonths(-$m).ToString("yyyy-MM")
    try { Invoke-WebRequest "https://download.db-ip.com/free/dbip-city-lite-$ym.mmdb.gz" -OutFile "$Repo\tools\dbip.mmdb.gz" -UseBasicParsing; $ok = $true; Write-Host "downloaded $ym"; break }
    catch { Write-Host "not available: $ym" }
  }
  if ($ok) {
    $in  = [IO.File]::OpenRead("$Repo\tools\dbip.mmdb.gz")
    $gz  = New-Object IO.Compression.GZipStream($in, [IO.Compression.CompressionMode]::Decompress)
    $out = [IO.File]::Create("$Repo\tools\dbip.mmdb")
    $gz.CopyTo($out); $out.Close(); $gz.Close(); $in.Close()
    Remove-Item "$Repo\tools\dbip.mmdb.gz"
    if ((Get-Item "$Repo\tools\dbip.mmdb").Length -lt 1MB) { Write-Host "Location database looks too small, deleting it." -ForegroundColor Yellow; Remove-Item "$Repo\tools\dbip.mmdb" }
  }
}

# ---------- 6. wake word (optional) ----------
$NpuDir = "$Repo\tools\npu"
if ($useWake -and -not (Test-Path "$NpuDir\.venv\Scripts\python.exe")) {
  $ProgressPreference = 'SilentlyContinue'
  Set-Location $NpuDir
  uv venv --python 3.12 .venv
  $vp = "$NpuDir\.venv\Scripts\python.exe"
  uv pip install --python $vp sounddevice openwakeword==0.6.0
  if ($LASTEXITCODE -ne 0) { Write-Host "Wake word packages FAILED to install. Wake word will not work (it is optional)." -ForegroundColor Red }
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
      if ((Get-FileHash "$md\$f" -Algorithm SHA256).Hash.ToLower() -ne $hashes[$f]) { Remove-Item "$md\$f"; Write-Host "HASH MISMATCH for $f - file deleted" -ForegroundColor Red }
      else { Write-Host "downloaded and verified $f" }
    } catch { Write-Host "FAILED to download $f" -ForegroundColor Red }
  }
  Set-Location $Repo
}

# ---------- 7. voice model ----------
Write-Host ""; Write-Host "Step 7: voice model (Kokoro, a few minutes)" -ForegroundColor Cyan
uv run --no-sync python -c "from huggingface_hub import snapshot_download; snapshot_download('hexgrad/Kokoro-82M'); print('voice model ready')"

# ---------- 8. Hue (optional) ----------
if ($useHue) {
  Write-Host ""; Write-Host "Step 8: Philips Hue" -ForegroundColor Cyan
  $ip = (Read-Host "IP address of your Hue bridge (Hue app > Settings > Bridge)").Trim()
  if ($ip -match '^\d{1,3}(\.\d{1,3}){3}$') {
    [Environment]::SetEnvironmentVariable('HUE_BRIDGE_IP', $ip, 'User')
    Read-Host "Press the round button on top of the Hue bridge, THEN press Enter here"
    try {
      $r = Invoke-RestMethod -Method Post -Uri "http://$ip/api" -Body '{"devicetype":"ironman_jarvis#pc"}' -ContentType 'application/json'
      if ($r[0].success) { [System.IO.File]::WriteAllText("$Cfg\hue-key.txt", $r[0].success.username, $Utf8); Write-Host "Hue key saved (stays on this PC only)." -ForegroundColor Green }
      else { Write-Host "Bridge answered: $($r | ConvertTo-Json -Compress)  (did you press the button in time? run this script again)" -ForegroundColor Yellow }
    } catch { Write-Host "Could not reach the bridge at $ip. Check the address and run this script again." -ForegroundColor Yellow }
  } else { Write-Host "That does not look like an IP address. Skipped Hue; run this script again." -ForegroundColor Yellow }
}

# ---------- 9. Tado (optional) ----------
if ($useTado) {
  Write-Host ""; Write-Host "Step 9: Tado login" -ForegroundColor Cyan
  Write-Host "A link appears. Open it in your browser and approve the login."
  uv run --no-sync python tools\tado_login.py
}

# ---------- 10. web search key (optional) + desktop shortcut ----------
Write-Host ""
$sec = Read-Host "Optional: paste your Firecrawl API key for web search (firecrawl.dev, typed hidden, Enter to skip)" -AsSecureString
$key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
if ($key) { [Environment]::SetEnvironmentVariable("FIRECRAWL_API_KEY", $key, "User"); [Environment]::SetEnvironmentVariable("OPENJARVIS_WEB_SEARCH_ENGINE", "firecrawl", "User"); Write-Host "key saved as a user environment variable (never in a file)" }
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Jarvis.lnk")
$s.TargetPath = "powershell.exe"
$s.Arguments = "-ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Repo\start-jarvis.ps1`""
$s.WorkingDirectory = $Repo
$ico = Join-Path $Repo "assets\jarvis.ico"
if (Test-Path $ico) { $s.IconLocation = $ico } else { $s.IconLocation = "powershell.exe,0" }   # J.A.R.V.I.S. icon for the desktop shortcut
$s.Save()

# ---------- final checks ----------
Write-Host ""; Write-Host "Checks:" -ForegroundColor Cyan
Chk "lms (LM Studio command)" ((Have lms) -or (Test-Path "$env:USERPROFILE\.lmstudio\bin\lms.exe")) "open LM Studio once, then run: lms bootstrap"
Chk "nvidia-smi" (Have nvidia-smi) "no NVIDIA GPU: the GPU gauges will not work, the rest does"
Chk "settings file" (Test-Path $cfgFile) "rerun this script"
Chk "wake word environment" (Test-Path "$NpuDir\.venv\Scripts\python.exe") "optional"
Write-Host ""
Write-Host "Still to do by hand:" -ForegroundColor Yellow
Write-Host " 1. Open LM Studio once, then in PowerShell run: lms bootstrap  (open a NEW PowerShell afterwards)"
Write-Host " 2. In LM Studio download the model google/gemma-4-26b-a4b-qat (about 16 GB; small PC? take google/gemma-4-e2b instead)"
Write-Host " 3. Double-click the Jarvis icon on your desktop. In your browser allow the microphone and remember the decision."
Write-Host "Done." -ForegroundColor Green
