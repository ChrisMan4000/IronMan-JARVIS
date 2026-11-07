# Optional online search for a newer language model that fits this PC (read-only: it only asks Hugging Face, changes nothing).
# Looks at the newest GGUF chat models of the LM Studio community (https://huggingface.co/lmstudio-community) and scores each one
# that fits this PC (0-100) on four things; the best score is suggested:
#   size        up to 30 points  the bigger model that still fits the graphics memory (or the RAM when there is no NVIDIA card) answers better
#   recency     up to 25 points  newer models score higher (the points halve about every 3 months)
#   popularity  up to 20 points  downloads and likes, compared with the other models in the list (log scale, so a new model is not crushed)
#   Jarvis fit  up to 25 points  what Jarvis needs: a model family known to call tools (Hue, Sonos, web search ...), an instruction/chat
#                                tuned model, text only, and actual .gguf files in the repository (checked for the winner)
# Size is estimated from the name (billions of parameters x 0.62 GB + 0.5), so it is a guess; the installer tests the model after the download.
# Output lines (with -Out written to that file):
#   BEST|<huggingface repo>|<estimated GB>|<date>|<score>|<short reason>     the winner
#   NONE|<reason>
param([string]$Out = '', [double]$Vram = -1, [double]$Ram = -1)
# the wizard copies jarvis-common.ps1 next to this file
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$resultFile = $Out
function Write-SearchResult([string]$Line) { if ($resultFile) { [System.IO.File]::WriteAllLines($resultFile, [string[]]@($Line)) } else { $Line } }
$inv = [Globalization.CultureInfo]::InvariantCulture
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  if ($Vram -lt 0 -or $Ram -lt 0) { $hw = Get-HardwareInfo; if ($Vram -lt 0) { $Vram = $hw.Vram }; if ($Ram -lt 0) { $Ram = $hw.Ram } }
  if ($Vram -ge 4) { $budget = $Vram * 0.75 - 1 } else { $budget = [math]::Min($Ram * 0.3, 2) }   # processor only: about 2 GB (a 2B model); bigger ones took minutes per answer on a Snapdragon laptop   # leaves room for the context, Whisper and the voice
  $list = Invoke-RestMethod -Uri 'https://huggingface.co/api/models?author=lmstudio-community&sort=createdAt&direction=-1&limit=100' -TimeoutSec 25
  # model families known to call tools well (higher = more reliable in Jarvis); anything else is ignored
  $families = @(
    @{ re = '(?i)qwen3|gpt-oss|glm-4|nemotron'; pts = 15 },
    @{ re = '(?i)qwen2\.5|llama-3|gemma-[34]|ministral|mistral|granite|hermes'; pts = 12 },
    @{ re = '(?i)qwen|gemma|llama|phi'; pts = 8 })
  $skip = '(?i)embed|(?<![a-z])vl(?![a-z])|vision|coder|guard|reward|ocr|base|distill|(?<![a-z])r1(?![a-z0-9])|math|translate|safeguard'
  $cand = @()
  foreach ($m in $list) {
    $id = "$($m.id)"
    if ($id -notmatch '-GGUF$' -or $id -match $skip) { continue }
    if ($m.pipeline_tag -and "$($m.pipeline_tag)" -ne 'text-generation') { continue }
    $fam = $families | Where-Object { $id -match $_.re } | Select-Object -First 1
    if (-not $fam) { continue }
    $pm = [regex]::Match(($id -split '/')[-1], '(?<![\d.])(\d+(?:\.\d+)?)[bB](?![a-zA-Z])')
    if (-not $pm.Success) { continue }
    $gb = [math]::Round([double]::Parse($pm.Groups[1].Value, $inv) * 0.62 + 0.5, 1)
    if ($gb -gt $budget -or $gb -lt 1) { continue }
    $created = [datetime]::MinValue
    if (-not [datetime]::TryParse("$($m.createdAt)", $inv, [Globalization.DateTimeStyles]::AdjustToUniversal, [ref]$created)) { $created = (Get-Date).AddYears(-1) }
    $age = [math]::Max(0, ((Get-Date).ToUniversalTime() - $created).TotalDays)
    $dl = 0.0; if ($m.downloads) { $dl = [double]$m.downloads }
    $lk = 0.0; if ($m.likes) { $lk = [double]$m.likes }
    $name = ($id -split '/')[-1]
    $jarvis = $fam.pts
    if ($name -match '(?i)instruct|-it(?![a-z])|chat|thinking') { $jarvis += 7 }   # tuned to follow instructions and chat
    if (@($m.tags) -match '(?i)tool') { $jarvis += 3 }                              # the repository itself says tool use
    $cand += [pscustomobject]@{ id = $id; gb = $gb; created = $created; age = $age; dl = $dl; lk = $lk; jarvis = [math]::Min(25, $jarvis); score = 0.0; why = '' }
  }
  if ($cand.Count -eq 0) { Write-SearchResult 'NONE|no suitable model among the newest ones'; exit 0 }
  $maxDl = [math]::Max(1, ($cand | Measure-Object -Property dl -Maximum).Maximum)
  $maxLk = [math]::Max(1, ($cand | Measure-Object -Property lk -Maximum).Maximum)
  foreach ($c in $cand) {
    $sSize = 30 * [math]::Pow($c.gb / $budget, 0.6)
    $sNew  = 25 * [math]::Exp(-$c.age / 130)
    $sPop  = 20 * (0.7 * [math]::Log(1 + $c.dl) / [math]::Log(1 + $maxDl) + 0.3 * [math]::Log(1 + $c.lk) / [math]::Log(1 + $maxLk))
    $c.score = [math]::Round($sSize + $sNew + $sPop + $c.jarvis, 1)
    $c.why = ('size {0:N0}/30, new {1:N0}/25, popular {2:N0}/20, Jarvis fit {3:N0}/25' -f $sSize, $sNew, $sPop, $c.jarvis)
  }
  # the winner must really have .gguf files; if not, the next best is checked (max 5 tries)
  $best = $null
  foreach ($c in ($cand | Sort-Object score -Descending | Select-Object -First 5)) {
    try {
      $info = Invoke-RestMethod -Uri ("https://huggingface.co/api/models/{0}" -f $c.id) -TimeoutSec 20
      if (@($info.siblings | Where-Object { "$($_.rfilename)" -match '\.gguf$' -and "$($_.rfilename)" -notmatch 'mmproj' }).Count -gt 0) { $best = $c; break }
    } catch { }
  }
  if (-not $best) { Write-SearchResult 'NONE|no model with downloadable files found'; exit 0 }
  Write-SearchResult (("BEST|{0}|{1}|{2}|{3}|{4}" -f $best.id, $best.gb.ToString($inv), $best.created.ToString('yyyy-MM-dd'), $best.score.ToString($inv), $best.why))
} catch { Write-SearchResult ('NONE|' + ($_.Exception.Message -replace '[\r\n|]', ' ')); exit 1 }
exit 0
