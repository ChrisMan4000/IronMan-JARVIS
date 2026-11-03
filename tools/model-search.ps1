# Optional online search for a newer language model that fits this PC (read-only: it only asks Hugging Face, changes nothing).
# Looks at the newest GGUF chat models of the LM Studio community (https://huggingface.co/lmstudio-community) and picks the
# biggest one that fits the graphics memory (or the RAM when there is no NVIDIA card). Size is estimated from the name (billions
# of parameters x 0.62 GB + 0.5), so it is a guess; the installer tests the model after the download.
# Output lines (with -Out written to that file):  BEST|<huggingface repo>|<estimated GB>|<date>   or   NONE|<reason>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Out', Justification = 'used by function Put; the rule does not look inside nested functions')]
param([string]$Out = '', [double]$Vram = -1, [double]$Ram = -1)
function Put($lines) { if ($Out) { [System.IO.File]::WriteAllLines($Out, [string[]]$lines) } else { $lines } }
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  if ($Vram -lt 0) {
    $Vram = 0
    $smi = (Get-Command nvidia-smi -ErrorAction SilentlyContinue).Source
    if (-not $smi) { foreach ($c in "$env:windir\Sysnative\nvidia-smi.exe", "$env:ProgramW6432\NVIDIA Corporation\NVSMI\nvidia-smi.exe") { if (Test-Path $c) { $smi = $c; break } } }
    if ($smi) { try { $v = (& $smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1); if ($v) { $Vram = [math]::Round([double]("$v".Trim()) / 1024) } } catch { $Vram = 0 } }
  }
  if ($Ram -lt 0) { $Ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) }
  if ($Vram -ge 4) { $budget = $Vram * 0.75 - 1 } else { $budget = [math]::Min($Ram * 0.3, 2) }   # processor only: about 2 GB (a 2B model); bigger ones took minutes per answer on a Snapdragon laptop   # leaves room for the context, Whisper and the voice
  $list = Invoke-RestMethod -Uri 'https://huggingface.co/api/models?author=lmstudio-community&sort=createdAt&direction=-1&limit=100' -TimeoutSec 25
  $family = '(?i)qwen|gemma|llama|gpt-oss|mistral|ministral|glm|granite|hermes|phi|nemotron'   # families known to call tools
  $skip = '(?i)embed|vl|vision|coder|guard|reward|ocr|base|distill|r1'
  $best = $null
  foreach ($m in $list) {
    $id = "$($m.id)"
    if ($id -notmatch '-GGUF$' -or $id -notmatch $family -or $id -match $skip) { continue }
    if ($m.pipeline_tag -and "$($m.pipeline_tag)" -ne 'text-generation') { continue }
    $pm = [regex]::Match(($id -split '/')[-1], '(?<![\d.])(\d+(?:\.\d+)?)[bB](?![a-zA-Z])')
    if (-not $pm.Success) { continue }
    $gb = [math]::Round([double]::Parse($pm.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) * 0.62 + 0.5, 1)
    if ($gb -gt $budget -or $gb -lt 1) { continue }
    $date = "$($m.createdAt)".Substring(0, [math]::Min(10, "$($m.createdAt)".Length))
    if (-not $best -or $gb -gt $best.gb) { $best = @{ id = $id; gb = $gb; date = $date } }
  }
  if ($best) { Put @(("BEST|{0}|{1}|{2}" -f $best.id, $best.gb.ToString([Globalization.CultureInfo]::InvariantCulture), $best.date)) }
  else { Put @('NONE|no suitable model among the newest ones') }
} catch { Put @('NONE|' + ($_.Exception.Message -replace '[\r\n|]', ' ')) }
