# Voice recommendation for IronMan J.A.R.V.I.S.: looks at the PC (NVIDIA GPU memory, RAM, ARM) and suggests
#   - a Whisper size for speech recognition (faster-whisper)
#   - a voice for answers: Kokoro (light, CPU) or Chatterbox (NVIDIA GPU, nicer, optional own voice clip)
# Read-only: it changes nothing. Used in two ways:
#   1. dot-sourced by tools\voice-setup.ps1 (functions Get-HwInfo, Get-VoiceRec, $VoiceWhisperOptions)
#   2. run by the Windows installer wizard: powershell -File voice-rec.ps1 -RecOut <file> -RecLlmGB <size of the chosen language model>
#      -> writes the lines  HW|vramGB|ramGB|nvidia 0/1|arm 0/1   WREC|<whisper size>   TREC|<kokoro or chatterbox>   FREE|<GB>
# NOTE: parameter names start with Rec on purpose: dot-sourcing must not overwrite variables of the calling script.
# The memory numbers are rough estimates (large-v3 measured on an RTX 5090: Whisper large-v3 plus Chatterbox used about 8 GB together).
param([string]$RecOut = '', [double]$RecLlmGB = -1)

function Get-HwInfo {
  $vram = 0; $nv = $false
  try {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
      $v = (nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
      if ($v) { $vram = [math]::Round([double]("$v".Trim()) / 1024); $nv = ($vram -gt 0) }
    }
  } catch { $vram = 0; $nv = $false }
  $ram = 0
  try { $ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) } catch { $ram = 0 }
  $arm = ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') -or ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64')
  return @{ Vram = $vram; Ram = $ram; Nvidia = $nv; Arm = $arm }
}

# Whisper sizes: download size and rough GPU memory (float16). Links: https://github.com/SYSTRAN/faster-whisper and
# https://github.com/openai/whisper#available-models-and-languages
$VoiceWhisperOptions = @(
  @{ id = 'tiny';     dl = '0.08'; vram = '1';   note = 'fastest, makes many mistakes' },
  @{ id = 'base';     dl = '0.15'; vram = '1';   note = 'fine for clear speech on weak PCs' },
  @{ id = 'small';    dl = '0.5';  vram = '2';   note = 'good balance' },
  @{ id = 'medium';   dl = '1.5';  vram = '3.5'; note = 'very accurate' },
  @{ id = 'large-v3'; dl = '3.1';  vram = '5';   note = 'most accurate, needs a strong NVIDIA card' }
)

# $llm = size in GB of the language model that will share the graphics card (-1 = guess from the card size)
function Get-VoiceRec($hw, [double]$llm) {
  if ($llm -lt 0) { if ($hw.Vram -ge 22) { $llm = 14.6 } elseif ($hw.Vram -ge 10) { $llm = 6.7 } else { $llm = 2.5 } }
  # the language model needs its file size plus about 1.5 GB for the context (26B model: file 14.6 GB, measured 15.9 GB)
  $free = [double]$hw.Vram - ($llm + 1.5)
  $chat = ($hw.Nvidia -and ($free -ge 9))                   # Chatterbox about 4 GB + Whisper small or more + safety margin
  $ttsGb = 0; if ($chat) { $ttsGb = 4 }
  $avail = $free - $ttsGb - 1
  $gpuOk = ($hw.Nvidia -and ($free -ge 2))
  if ($gpuOk) {
    if ($avail -ge 5) { $w = 'large-v3' } elseif ($avail -ge 3.5) { $w = 'medium' } elseif ($avail -ge 2) { $w = 'small' } else { $w = 'base' }
    $dev = 'cuda'; $comp = 'float16'
  } else {
    # no usable NVIDIA memory: the processor does the work (int8). ARM and PCs with under 16 GB RAM get the lighter size.
    if ($hw.Arm -or ($hw.Ram -gt 0 -and $hw.Ram -lt 16)) { $w = 'base' } else { $w = 'small' }
    $dev = 'cpu'; $comp = 'int8'
  }
  $t = 'kokoro'; if ($chat) { $t = 'chatterbox' }
  return @{ Whisper = $w; Device = $dev; Compute = $comp; Tts = $t; Free = [math]::Round($free, 1); GpuOk = $gpuOk }
}

if ($RecOut) {
  $hw = Get-HwInfo
  $r = Get-VoiceRec $hw $RecLlmGB
  $nvf = 0; if ($hw.Nvidia) { $nvf = 1 }
  $armf = 0; if ($hw.Arm) { $armf = 1 }
  $lines = @(
    ("HW|{0}|{1}|{2}|{3}" -f $hw.Vram, $hw.Ram, $nvf, $armf),
    ("WREC|{0}" -f $r.Whisper),
    ("TREC|{0}" -f $r.Tts),
    ("FREE|{0}" -f $r.Free.ToString([Globalization.CultureInfo]::InvariantCulture))
  )
  [System.IO.File]::WriteAllLines($RecOut, [string[]]$lines)
}
