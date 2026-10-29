# Helper for the Windows installer wizard (model page): writes one line "REC|tier|gpuGB|ramGB" and one line "modelKey|sizeGB" per
# language model already in LM Studio. Read-only; changes nothing. Same recommendation rule as Step 6b of install-jarvis.ps1.
param([string]$Out)
$lines = @()
$vram = 0
try { if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { $vram = [math]::Round([double]((nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1).Trim()) / 1024) } } catch { $vram = 0 }
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($vram -ge 22) { $rec = 3 } elseif ($vram -ge 10) { $rec = 2 } elseif ($vram -eq 0 -and $ram -ge 24) { $rec = 2 } else { $rec = 1 }
$lines += "REC|$rec|$vram|$ram"
$lms = $null
if (Get-Command lms -ErrorAction SilentlyContinue) { $lms = 'lms' } elseif (Test-Path "$env:USERPROFILE\.lmstudio\bin\lms.exe") { $lms = "$env:USERPROFILE\.lmstudio\bin\lms.exe" }
if ($lms) {
  try {
    $j = (& $lms ls --json 2>$null) -join "`n"
    $arr = ConvertFrom-Json $j      # PowerShell 5 returns the array as ONE object: loop over it
    foreach ($m in $arr) { if ($m.type -eq 'llm' -and $m.modelKey) { $lines += ("{0}|{1}" -f $m.modelKey, [math]::Round($m.sizeBytes / 1GB, 1).ToString([Globalization.CultureInfo]::InvariantCulture)) } }
  } catch { }
}
if ($Out) { [System.IO.File]::WriteAllLines($Out, [string[]]$lines) }
