# Helper for the Windows installer wizard (model page). Read-only: it changes nothing. Writes these lines to -Out:
#   REC|<tier>|<gpuGB>|<ramGB>                         the size recommended for this PC (rule: Get-RecommendedModelTier)
#   TIER|<tier>|<model id>|<LM Studio key>|<GB>|<note>   the three sizes install-jarvis.ps1 can download
#   MODEL|<LM Studio key>|<GB>                         one line per language model already in LM Studio
param([Parameter(Mandatory = $true)][string]$Out)
# the wizard copies jarvis-common.ps1 next to this file; in the project it lives in tools\
$common = Join-Path $PSScriptRoot 'jarvis-common.ps1'
if (-not (Test-Path $common)) { $common = Join-Path $PSScriptRoot '..\tools\jarvis-common.ps1' }
. $common
$inv = [Globalization.CultureInfo]::InvariantCulture
$hw = Get-HardwareInfo
$lines = @('REC|{0}|{1}|{2}' -f (Get-RecommendedModelTier $hw.Vram).Tier, $hw.Vram, $hw.Ram)
foreach ($t in $JarvisModelTiers) { $lines += 'TIER|{0}|{1}|{2}|{3}|{4}' -f $t.Tier, $t.Id, $t.Key, $t.Gb.ToString($inv), $t.Note }
foreach ($m in (Get-LlmModel (Get-LmsCommand))) { $lines += 'MODEL|{0}|{1}' -f $m.modelKey, ([math]::Round($m.sizeBytes / 1GB, 1)).ToString($inv) }
[System.IO.File]::WriteAllLines($Out, [string[]]$lines)
exit 0
