# Voice recommendation ("rec") for the Windows installer wizard: looks at the PC (NVIDIA graphics memory, RAM, ARM) and suggests
#   - a Whisper size for speech recognition (faster-whisper)
#   - a voice for the answers: Kokoro (light, any PC) or Chatterbox (NVIDIA card, nicer, can copy a voice clip)
# Read-only: it changes nothing. The rules live in tools\jarvis-common.ps1 (Get-VoiceRecommendation), shared with tools\voice-setup.ps1.
#   powershell -File voice-rec.ps1 -Out <file> -LlmGB <size of the chosen language model, -1 = guess>
# Lines written to -Out:
#   HW|<gpuGB>|<ramGB>|<nvidia 0/1>|<arm 0/1>   WHISPER|<size>   VOICE|<kokoro or chatterbox>   FREE|<GB of graphics memory left>
#   WOPT|<size>|<download GB>|<graphics memory GB>|<note>   one line per Whisper size, in order
param([Parameter(Mandatory = $true)][string]$Out, [double]$LlmGB = -1)
# the wizard copies jarvis-common.ps1 next to this file
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$inv = [Globalization.CultureInfo]::InvariantCulture
$hw = Get-HardwareInfo
$advice = Get-VoiceRecommendation $hw $LlmGB
$lines = @(
  ('HW|{0}|{1}|{2}|{3}' -f $hw.Vram, $hw.Ram, [int]$hw.Nvidia, [int]$hw.Arm),
  ('WHISPER|{0}' -f $advice.Whisper),
  ('VOICE|{0}' -f $advice.Tts),
  ('FREE|{0}' -f $advice.Free.ToString($inv))
)
foreach ($o in $JarvisWhisperOptions) { $lines += 'WOPT|{0}|{1}|{2}|{3}' -f $o.Id, $o.Download.ToString($inv), $o.Vram.ToString($inv), $o.Note }
[System.IO.File]::WriteAllLines($Out, [string[]]$lines)
exit 0
