# Contract tests between the PowerShell helpers and the Inno Setup wizard (installer\ironman-jarvis.iss):
# the line formats the scripts write must be the ones the wizard reads, and shared lists must not drift apart.
# list-llms.ps1 and voice-rec.ps1 only read the PC (graphics card, RAM, LM Studio's model list); they change nothing.
#   powershell -NoProfile -Command "Invoke-Pester -Script tests\powershell"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $here '..\..')
. (Join-Path $root 'tools\jarvis-common.ps1')
$iss = [System.IO.File]::ReadAllText((Join-Path $root 'installer\ironman-jarvis.iss'))
$tmp = Join-Path $env:TEMP ('jarvis-contract-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $tmp | Out-Null

Describe 'installer\list-llms.ps1 -> wizard model page' {
  $out = Join-Path $tmp 'llms.txt'
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'installer\list-llms.ps1') -Out $out
  $code = $LASTEXITCODE
  $lines = @(Get-Content $out)
  It 'ends with exit code 0' { $code | Should Be 0 }
  It 'writes only REC, TIER and MODEL lines' { @($lines | Where-Object { $_ -notmatch '^(REC|TIER|MODEL)\|' }).Count | Should Be 0 }
  It 'writes one REC line with a tier from 1 to 3' { @($lines | Where-Object { $_ -match '^REC\|[123]\|\d+\|\d+$' }).Count | Should Be 1 }
  It 'writes the three tiers of jarvis-common.ps1' {
    $t = @($lines | Where-Object { $_ -like 'TIER|*' })
    $t.Count | Should Be 3
    for ($i = 0; $i -lt 3; $i++) { ($t[$i] -split '\|')[2] | Should Be $JarvisModelTiers[$i].Id }
  }
  It 'is read by the wizard (all three tags)' { foreach ($tag in 'REC|', 'TIER|', 'MODEL|') { $iss.Contains("Pos('$tag', L) = 1") | Should Be $true } }
}

Describe 'tools\voice-rec.ps1 -> wizard voice page' {
  $out = Join-Path $tmp 'voice.txt'
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\voice-rec.ps1') -Out $out -LlmGB 6.7
  $code = $LASTEXITCODE
  $lines = @(Get-Content $out)
  It 'ends with exit code 0' { $code | Should Be 0 }
  It 'writes only the known tags' { @($lines | Where-Object { $_ -notmatch '^(HW|WHISPER|VOICE|FREE|WOPT)\|' }).Count | Should Be 0 }
  It 'lists every Whisper size, in order' {
    $ids = @($lines | Where-Object { $_ -like 'WOPT|*' } | ForEach-Object { ($_ -split '\|')[1] })
    ($ids -join ',') | Should Be ($JarvisWhisperIds -join ',')
  }
  It 'recommends a known size and voice' {
    ($JarvisWhisperIds -contains (($lines | Where-Object { $_ -like 'WHISPER|*' }) -split '\|')[1]) | Should Be $true
    ($JarvisVoiceBackends -contains (($lines | Where-Object { $_ -like 'VOICE|*' }) -split '\|')[1]) | Should Be $true
  }
  It 'is read by the wizard (all tags)' { foreach ($tag in 'HW|', 'WHISPER|', 'VOICE|', 'FREE|', 'WOPT|') { $iss.Contains("Pos('$tag', L) = 1") | Should Be $true } }
}

Describe 'wizard <-> install-jarvis.ps1' {
  It 'ships jarvis-common.ps1 with the helper scripts it runs from its temp folder' {
    $iss.Contains('Source: "..\tools\jarvis-common.ps1"; Flags: dontcopy') | Should Be $true
    ([regex]::Matches($iss, "ExtractTemporaryFile\('jarvis-common.ps1'\)")).Count | Should Be 3
  }
  It 'passes only model tiers that exist' {
    foreach ($m in [regex]::Matches($iss, '-ModelTier (\d)')) { @($JarvisModelTiers | Where-Object { "$($_.Tier)" -eq $m.Groups[1].Value }).Count | Should Be 1 }
  }
  It 'reads the status lines install-jarvis.ps1 writes (STEP and EXIT)' { $iss.Contains("Pos('STEP ', L) = 1") -and $iss.Contains("Pos('EXIT|', L) = 1") | Should Be $true }
  It 'removes the same user settings as jarvis-common.ps1 lists' { foreach ($n in $JarvisUserEnvVars) { $iss.Contains("'$n'") | Should Be $true } }
  It 'uses the uninstall helper that exists' { Test-Path (Join-Path $root 'tools\remove-windows-parts.ps1') | Should Be $true; $iss.Contains('remove-windows-parts.ps1') | Should Be $true }
}

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
