# Downloads, tests and loads the language model IN THE BACKGROUND, so the installer can finish and Jarvis can be started meanwhile.
# Started by install-jarvis.ps1 (hidden, not as a child of it). Progress is written to %USERPROFILE%\.openjarvis\model-download.txt as
#   <state>|<text>|<process id>|<target>      state = downloading, testing, loading, done or failed
# Order: the model found online (-OnlineModel, tested for tool calls), then the size chosen in the wizard (-ModelTier).
# When the online download is refused by LM Studio's catalog (brand-new models are not listed yet), the .gguf file is downloaded
# straight from Hugging Face into LM Studio's models folder instead.
param(
  [Parameter(Mandatory = $true)][string]$Lms,
  [string]$OnlineModel = '',   # Hugging Face repo, e.g. lmstudio-community/Qwen3.5-4B-GGUF
  [int]$ModelTier = 0,         # 1-3, see $JarvisModelTiers in jarvis-common.ps1
  [string]$InterimId = ''      # a model that was loaded by the installer meanwhile: it is only replaced when Jarvis is not running
)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$StateFile = Join-Path $JarvisConfigDir 'model-download.txt'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$script:Target = if ($OnlineModel) { $OnlineModel } else { ($JarvisModelTiers | Where-Object { $_.Tier -eq $ModelTier } | Select-Object -First 1).Id }
function Set-State([string]$State, [string]$Text) {
  try { [System.IO.File]::WriteAllText($StateFile, ("{0}|{1}|{2}|{3}" -f $State, ($Text -replace '[\r\n|]', ' '), $PID, $script:Target), $Utf8) } catch { }
}
New-Item -ItemType Directory -Force $JarvisConfigDir | Out-Null
Set-State 'downloading' 'starting'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$inv = [Globalization.CultureInfo]::InvariantCulture

function Get-NewModelKey([string[]]$Before) {
  return @(Get-LlmModel $Lms | Where-Object { $Before -notcontains $_.modelKey } | Select-Object -First 1)
}
function Invoke-LmsGet([string]$Source, [string[]]$ExtraArgs) {
  # lms get with the download percentage copied to the state file
  $script:lastP = ''; $script:lastT = Get-Date
  & $Lms get $Source @ExtraArgs -y 2>&1 | ForEach-Object {
    $pm = [regex]::Matches("$_", '(\d{1,3}(?:\.\d+)?)\s?%')
    if ($pm.Count -gt 0) {
      $p = $pm[$pm.Count - 1].Groups[1].Value
      if ($p -ne $script:lastP -and ((Get-Date) - $script:lastT).TotalSeconds -ge 3) { Set-State 'downloading' "$p%"; $script:lastP = $p; $script:lastT = Get-Date }
    }
  }
  return $LASTEXITCODE
}
function Save-HfGguf([string]$Repo) {
  # fallback: one .gguf file straight from Hugging Face into LM Studio's models folder (curl.exe ships with Windows 10/11, resumes with -C -)
  try {
    $info = Invoke-RestMethod -Uri "https://huggingface.co/api/models/${Repo}?blobs=true" -TimeoutSec 30
    $files = @($info.siblings | Where-Object { "$($_.rfilename)" -match '\.gguf$' -and "$($_.rfilename)" -notmatch 'mmproj|/' })
    if ($files.Count -eq 0) { return $false }
    $pick = $null
    foreach ($pat in 'Q4_K_M', 'Q4_K_S', 'Q4_0', 'QAT', 'Q5_K_M', 'Q6_K', 'Q8_0') { $pick = $files | Where-Object { "$($_.rfilename)" -match $pat } | Select-Object -First 1; if ($pick) { break } }
    if (-not $pick) { $pick = $files | Sort-Object size | Select-Object -First 1 }
    $dir = Join-Path $env:USERPROFILE (".lmstudio\models\" + ($Repo -replace '/', '\'))
    New-Item -ItemType Directory -Force $dir | Out-Null
    $dest = Join-Path $dir "$($pick.rfilename)"
    $total = [double]$pick.size
    $cp = Start-Process curl.exe -ArgumentList @('-L', '-C', '-', '--fail', '-s', '-o', "`"$dest`"", "https://huggingface.co/$Repo/resolve/main/$($pick.rfilename)") -WindowStyle Hidden -PassThru
    while (-not $cp.HasExited) {
      Start-Sleep -Seconds 3
      if ($total -gt 0 -and (Test-Path $dest)) { Set-State 'downloading' ("{0:N0}%" -f ([math]::Min(99, (Get-Item $dest).Length * 100 / $total))) }
    }
    if ($cp.ExitCode -ne 0) { Write-JarvisLog "curl download of $Repo/$($pick.rfilename) ended with code $($cp.ExitCode)"; return $false }
    return ((Get-Item $dest).Length -ge $total * 0.99)
  } catch { Write-JarvisLog "direct Hugging Face download of $Repo failed: $($_.Exception.Message)"; return $false }
}

$key = $null
# 1. the model found online
if ($OnlineModel -match '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$') {
  $before = @(Get-LlmModel $Lms | ForEach-Object { $_.modelKey })
  Set-State 'downloading' 'starting'
  [void](Invoke-LmsGet "https://huggingface.co/$OnlineModel" @('--gguf'))
  $new = Get-NewModelKey $before
  if ($new.Count -eq 0) {
    Write-JarvisLog "lms get could not download $OnlineModel, trying the file directly from Hugging Face"
    if (Save-HfGguf $OnlineModel) { Start-Sleep -Seconds 2; $new = Get-NewModelKey $before }
  }
  if ($new.Count -gt 0) {
    Set-State 'testing' "testing $($new[0].modelKey) for tool calls"
    if (Test-ModelToolCall $Lms $new[0].modelKey) { $key = $new[0].modelKey }
    else { Write-JarvisLog "online model $($new[0].modelKey) failed the tool-call test" }
  } else { Write-JarvisLog "online model $OnlineModel not downloaded" }
}
# 2. the size chosen in the wizard
if (-not $key -and $ModelTier -ge 1) {
  $tier = $JarvisModelTiers | Where-Object { $_.Tier -eq $ModelTier } | Select-Object -First 1
  if ($tier) {
    $script:Target = $tier.Id
    $before = @(Get-LlmModel $Lms | ForEach-Object { $_.modelKey })
    Set-State 'downloading' 'starting'
    [void](Invoke-LmsGet $tier.Id @())
    $newK = @(Get-LlmModel $Lms | Where-Object { $_.modelKey -eq $tier.Id -or $_.modelKey -eq $tier.Key -or ($before -notcontains $_.modelKey) } | Select-Object -First 1)
    if ($newK.Count -gt 0) { $key = $newK[0].modelKey }
  }
}
if (-not $key -or -not (Test-ModelId $key)) {
  Set-State 'failed' 'the download did not finish; open LM Studio, download a model there, or run the installer again'
  exit 1
}

# 3. load it (a running Jarvis server keeps its model: the new one is only remembered for the next start)
$parArg = @(); if (-not (Find-NvidiaSmi)) { $parArg = @('--parallel', '1') }   # processor only: one slot keeps the prompt cached
[System.IO.File]::WriteAllText((Join-Path $JarvisConfigDir 'jarvis-model.txt'), $key, $Utf8)
$serverUp = [bool](Get-NetTCPConnection -LocalPort $JarvisServerPort -State Listen -ErrorAction SilentlyContinue)
if ($InterimId -and $serverUp) { Set-State 'done' "$key is ready (Jarvis is running with $InterimId; it switches at the next start)"; exit 0 }
Set-State 'loading' "loading $key into memory"
if ($InterimId) { & $Lms unload --all 2>&1 | Out-Null }
& $Lms load $key -c 8192 -y @parArg 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Set-State 'failed' "$key is downloaded but could not be loaded (code $LASTEXITCODE)"; exit 1 }
Set-State 'done' "$key is loaded"
exit 0
