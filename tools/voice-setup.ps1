# Voice setup for IronMan J.A.R.V.I.S.: picks the Whisper size (speech recognition) and the voice (Kokoro or Chatterbox),
# downloads and TESTS them, and only then writes them into %USERPROFILE%\.openjarvis\config.toml ([speech] section).
# Called by install-jarvis.ps1 (voice step) and by the private restore-jarvis.ps1. Run it again any time to change the choice:
#   powershell -ExecutionPolicy Bypass -File tools\voice-setup.ps1 -Ask
# Never run 'uv sync' or a plain 'uv run' afterwards: they remove the hand-added GPU packages (use 'uv run --no-sync').
# Honest note: written from the working setup of the author's PC (RTX 5090), NOT yet tested on other PCs. Each part is tested
# after the install and the script falls back to the lighter choice (processor / Kokoro) when a test fails.
param(
  [string]$Repo = '',
  [string]$Whisper = '',        # tiny | base | small | medium | large-v3 (empty = recommendation)
  [string]$Tts = '',            # kokoro | chatterbox (empty = kokoro, or asks with -Ask)
  [string]$VoiceClip = '',      # optional .wav/.mp3/.flac of YOUR OWN voice for Chatterbox
  [double]$LlmGB = -1,          # size of the language model sharing the graphics card (-1 = guess)
  [switch]$Ask,                 # ask the questions in the console
  [string]$StatusFile = '',     # the Windows installer reads progress lines from this file ...
  [int]$StatusStep = 0          # ... shown as this step number (the caller's numbering; 0 = no progress lines)
)
$ErrorActionPreference = 'Continue'
if (-not $Repo) { $Repo = Split-Path -Parent $PSScriptRoot }
$Cfg = Join-Path $env:USERPROFILE '.openjarvis'
$cfgFile = Join-Path $Cfg 'config.toml'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$wizardStatus = $null; if ($StatusFile -and $StatusStep -gt 0) { $wizardStatus = @{ File = $StatusFile; Step = $StatusStep } }

function Write-VoiceStep([string]$Text) {
  # progress line for the console and, when the installer wizard runs this, for its progress bar
  Write-Host $Text -ForegroundColor Cyan
  if ($wizardStatus) { Write-WizardLine $wizardStatus.File ('STEP {0}|{1}' -f $wizardStatus.Step, $Text) }
}
# runs a small Python test inside the project environment; returns everything it printed (check it for the OK marker)
function Invoke-ProjectPython([string]$code, [string[]]$pyArgs) {
  $f = Join-Path $env:TEMP ('jarvis-voice-' + [guid]::NewGuid().ToString('N') + '.py')
  [System.IO.File]::WriteAllText($f, $code, $Utf8)
  Push-Location $Repo
  try { $o = & uv run --no-sync python $f @pyArgs 2>&1 } finally { Pop-Location; Remove-Item $f -ErrorAction SilentlyContinue }
  $txt = @($o | ForEach-Object { "$_" })
  $txt | Where-Object { $_ -notmatch 'FutureWarning|pynvml' } | Select-Object -Last 6 | ForEach-Object { Write-Host "    $_" }
  return ($txt -join "`n")
}
$pyWhisper = @'
import sys
import numpy as np
from faster_whisper import WhisperModel
m, d, c = sys.argv[1], sys.argv[2], sys.argv[3]
w = WhisperModel(m, device=d, compute_type=c)
list(w.transcribe(np.zeros(16000, dtype="float32"), language="en")[0])
print("WHISPER_OK")
'@
$pyChatterbox = @'
import sys
import torch
if not torch.cuda.is_available():
    print("NO_CUDA")
    sys.exit(2)
from chatterbox.mtl_tts import ChatterboxMultilingualTTS as M
M.from_pretrained(device="cuda")
print("CHATTERBOX_OK")
'@

Push-Location $Repo
try {
  # ---------- 1. look at the PC ----------
  $hw = Get-HardwareInfo
  $advice = Get-VoiceRecommendation $hw $LlmGB
  Write-Host ""
  if ($hw.Nvidia) {
    Write-Host ("  Your PC: NVIDIA GPU with {0} GB, RAM {1} GB. About {2} GB of graphics memory stay free next to the language model." -f $hw.Vram, $hw.Ram, $advice.Free)
  } else {
    Write-Host ("  Your PC: no NVIDIA GPU found, RAM {0} GB. Speech recognition runs on the processor; the Chatterbox voice needs an NVIDIA GPU." -f $hw.Ram)
  }
  if ($Whisper -and ($JarvisWhisperIds -notcontains $Whisper)) { Write-Host "  Unknown Whisper size '$Whisper', using the recommendation." -ForegroundColor Yellow; $Whisper = '' }
  if ($Tts -and ($JarvisVoiceBackends -notcontains $Tts)) { Write-Host "  Unknown voice '$Tts', using the recommendation." -ForegroundColor Yellow; $Tts = '' }

  # ---------- 2. choices ----------
  if ($Ask -and -not $Whisper) {
    Write-Host ""
    Write-Host "Speech recognition (Whisper through faster-whisper). Read more:" -ForegroundColor Cyan
    Write-Host "  https://github.com/SYSTRAN/faster-whisper"
    Write-Host "  https://github.com/openai/whisper#available-models-and-languages"
    $defaultIdx = 1
    for ($i = 0; $i -lt $JarvisWhisperOptions.Count; $i++) {
      $o = $JarvisWhisperOptions[$i]; $mark = ''
      if ($o.Id -eq $advice.Whisper) { $mark = '   <-- recommended for your PC'; $defaultIdx = $i + 1 }
      Write-Host ("   {0}) {1,-9} download about {2} GB, about {3} GB graphics memory - {4}{5}" -f ($i + 1), $o.Id, $o.Download, $o.Vram, $o.Note, $mark)
    }
    $n = (Read-Host "  Which size? (1-$($JarvisWhisperOptions.Count), Enter = $defaultIdx)").Trim()
    if ($n -eq '') { $n = "$defaultIdx" }
    if ($n -match '^\d+$' -and [int]$n -ge 1 -and [int]$n -le $JarvisWhisperOptions.Count) { $Whisper = $JarvisWhisperOptions[[int]$n - 1].Id }
  }
  if (-not $Whisper) { $Whisper = $advice.Whisper }

  if ($Ask -and -not $Tts) {
    Write-Host ""
    Write-Host "Voice for the answers. Read more:" -ForegroundColor Cyan
    Write-Host "  Kokoro      https://huggingface.co/hexgrad/Kokoro-82M   (one size only, 82 million parameters, runs on any PC, about 0.3 GB)"
    Write-Host "  Chatterbox  https://github.com/resemble-ai/chatterbox  (more natural, can copy a voice from a short clip of YOUR OWN voice; needs an NVIDIA GPU, about 4 GB graphics memory and up to 10 GB of disk space)"
    $mk = ''; if ($advice.Tts -eq 'kokoro') { $mk = '   <-- recommended for your PC' }
    Write-Host ("   1) Kokoro{0}" -f $mk)
    $mk = ''; if ($advice.Tts -eq 'chatterbox') { $mk = '   <-- recommended for your PC' }
    if ($hw.Nvidia) { Write-Host ("   2) Chatterbox{0}" -f $mk) } else { Write-Host "   2) Chatterbox   (not possible: no NVIDIA GPU found)" -ForegroundColor DarkGray }
    $defT = '1'; if ($advice.Tts -eq 'chatterbox') { $defT = '2' }
    $n = (Read-Host "  Which voice? (1-2, Enter = $defT)").Trim()
    if ($n -eq '') { $n = $defT }
    if ($n -eq '2') { $Tts = 'chatterbox' } else { $Tts = 'kokoro' }
    if ($Tts -eq 'chatterbox' -and -not $VoiceClip) {
      $VoiceClip = (Read-Host "  Optional: path of a .wav/.mp3/.flac clip of YOUR OWN voice (10-20 s, clear). Enter = the built-in voice").Trim().Trim('"')
    }
  }
  if (-not $Tts) { $Tts = 'kokoro' }
  if ($Tts -eq 'chatterbox' -and -not $hw.Nvidia) { Write-Host "  Chatterbox needs an NVIDIA GPU. Using Kokoro instead." -ForegroundColor Yellow; $Tts = 'kokoro' }

  $device = $advice.Device; $compute = $advice.Compute
  Write-Host ""
  Write-Host ("  Chosen: Whisper {0} on the {1}, voice {2}" -f $Whisper, $(if ($device -eq 'cuda') { 'graphics card' } else { 'processor' }), $Tts) -ForegroundColor Green

  # ---------- 3. install and test ----------
  if ($device -eq 'cuda' -or $Tts -eq 'chatterbox') {
    Write-VoiceStep "Voice: installing the NVIDIA GPU libraries (a few hundred MB)"
    uv pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" "av>=15,<17"
    if ($LASTEXITCODE -ne 0) { Write-Host "  The NVIDIA libraries could not be installed. The tests below show what still works." -ForegroundColor Yellow; Write-JarvisLog "voice: NVIDIA libraries install failed (code $LASTEXITCODE)" }
  }
  Write-VoiceStep "Voice: downloading and testing speech recognition (Whisper $Whisper)"
  $res = Invoke-ProjectPython $pyWhisper @($Whisper, $device, $compute)
  if (($res -notmatch 'WHISPER_OK') -and $device -eq 'cuda') {
    Write-Host "  Speech recognition on the graphics card did not work. Trying the processor (slower)." -ForegroundColor Yellow
    $device = 'cpu'; $compute = 'int8'
    if (@('medium', 'large-v3') -contains $Whisper) { $Whisper = 'small'; Write-Host "  Using the smaller size 'small' on the processor." -ForegroundColor Yellow }
    $res = Invoke-ProjectPython $pyWhisper @($Whisper, $device, $compute)
  }
  if ($res -notmatch 'WHISPER_OK') { Write-Host "  The speech recognition test failed (internet?). The setting is saved anyway; Jarvis tries again on first use." -ForegroundColor Yellow }

  Write-VoiceStep "Voice: downloading the Kokoro voice (about 0.3 GB)"
  uv run --no-sync python -c "from huggingface_hub import snapshot_download; snapshot_download('hexgrad/Kokoro-82M'); print('voice model ready')"
  if ($LASTEXITCODE -ne 0) { Write-Host "  Kokoro download failed. The first spoken answer will try again." -ForegroundColor Yellow }

  $voiceId = ''
  if ($Tts -eq 'chatterbox') {
    Write-VoiceStep "Voice: installing Chatterbox (several GB, this takes a long time)"
    uv pip install "chatterbox-tts==0.1.7"   # the version tested on the author's PC (it pins torch 2.6.0 and transformers 5.2.0; torch is upgraded right after)
    uv pip install --upgrade "torch>=2.7" "torchaudio>=2.7" --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { Write-JarvisLog "voice: torch upgrade failed (code $LASTEXITCODE); the Chatterbox test below decides" }
    Write-VoiceStep "Voice: loading Chatterbox once (downloads its model, about 3 GB)"
    $res = Invoke-ProjectPython $pyChatterbox @()
    if ($res -notmatch 'CHATTERBOX_OK') {
      Write-Host "  Chatterbox did not work on this PC (see the lines above). Using Kokoro instead. You can try again later with: powershell -ExecutionPolicy Bypass -File tools\voice-setup.ps1 -Ask" -ForegroundColor Yellow
      $Tts = 'kokoro'
    } elseif ($VoiceClip) {
      if ((Test-Path -LiteralPath $VoiceClip) -and ($VoiceClip -match '\.(wav|mp3|flac)$')) {
        try {
          $vd = Join-Path $Cfg 'voices'; New-Item -ItemType Directory -Force $vd | Out-Null
          $dest = Join-Path $vd (Split-Path $VoiceClip -Leaf)
          if ((Resolve-Path -LiteralPath $VoiceClip).Path -ne $dest) { Copy-Item -LiteralPath $VoiceClip $dest -Force }
          $voiceId = $dest.Replace('\', '/')
          Write-Host "  Voice clip copied to $dest (only use a voice you have permission to copy)." -ForegroundColor Green
        } catch { Write-Host "  Could not copy the voice clip ($($_.Exception.Message)). Using the built-in voice." -ForegroundColor Yellow }
      } else { Write-Host "  Voice clip not found or not a .wav/.mp3/.flac file. Using the built-in voice." -ForegroundColor Yellow }
    }
  }

  # ---------- 4. write the settings (only after the tests) ----------
  if (Test-Path $cfgFile) {
    if (-not (Test-Path "$cfgFile.before-voice")) { Copy-Item $cfgFile "$cfgFile.before-voice" }
    $c = [System.IO.File]::ReadAllText($cfgFile, [System.Text.Encoding]::UTF8)
    $cur = [regex]::Match((Get-SpeechBlock $c).Groups[1].Value, '(?m)^[ \t]*tts_backend[ \t]*=[ \t]*"([^"]*)"').Groups[1].Value
    $c = Merge-SpeechValue -text $c -key 'model' -value $Whisper
    $c = Merge-SpeechValue -text $c -key 'device' -value $device
    $c = Merge-SpeechValue -text $c -key 'compute_type' -value $compute
    $c = Merge-SpeechValue -text $c -key 'tts_backend' -value $Tts
    if ($Tts -eq 'chatterbox') { $c = Merge-SpeechValue -text $c -key 'voice_id' -value $voiceId }
    elseif ($cur -ne 'kokoro') { $c = Merge-SpeechValue -text $c -key 'voice_id' -value 'am_adam' }
    [System.IO.File]::WriteAllText($cfgFile, $c, $Utf8)
    Write-Host "  Saved to $cfgFile (backup of the old file: config.toml.before-voice)" -ForegroundColor Green
  } else { Write-Host "  No settings file found at $cfgFile - voice settings not saved." -ForegroundColor Yellow }
  Write-VoiceStep "Voice ready: Whisper $Whisper ($device), voice $Tts"
} finally { Pop-Location }
