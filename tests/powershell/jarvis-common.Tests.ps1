# Unit tests for tools\jarvis-common.ps1 (pure functions only: nothing on the PC is changed).
# Run in Windows PowerShell 5.1, which has Pester 3.4 built in:
#   powershell -NoProfile -Command "Invoke-Pester -Script tests\powershell"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here '..\..\tools\jarvis-common.ps1')

Describe 'Get-RecommendedModelTier' {
  It 'picks the small model without NVIDIA memory' { (Get-RecommendedModelTier 0).Tier | Should Be 1 }
  It 'keeps the small model below 10 GB' { (Get-RecommendedModelTier 9).Tier | Should Be 1 }
  It 'picks the medium model from 10 GB' { (Get-RecommendedModelTier 10).Tier | Should Be 2 }
  It 'keeps the medium model below 22 GB' { (Get-RecommendedModelTier 21).Tier | Should Be 2 }
  It 'picks the large model from 22 GB' { (Get-RecommendedModelTier 22).Tier | Should Be 3 }
  It 'has three tiers with valid model ids, growing in size' {
    $JarvisModelTiers.Count | Should Be 3
    foreach ($t in $JarvisModelTiers) { (Test-ModelId $t.Id) | Should Be $true; (Test-ModelId $t.Key) | Should Be $true }
    ($JarvisModelTiers[0].Gb -lt $JarvisModelTiers[1].Gb -and $JarvisModelTiers[1].Gb -lt $JarvisModelTiers[2].Gb) | Should Be $true
  }
}

Describe 'Test-ModelId' {
  It 'accepts LM Studio keys and Hugging Face ids' {
    (Test-ModelId 'google/gemma-4-26b-a4b-qat') | Should Be $true
    (Test-ModelId 'lmstudio-community/Qwen3.5-2B-GGUF') | Should Be $true
    (Test-ModelId 'qwen3.5-2b@q4_k_m') | Should Be $true
  }
  It 'refuses anything that could break a command line' {
    (Test-ModelId 'a b') | Should Be $false
    (Test-ModelId 'x;calc') | Should Be $false
    (Test-ModelId "x'y") | Should Be $false
    (Test-ModelId '') | Should Be $false
  }
}

Describe 'ConvertFrom-LmsList' {
  $json = '[{"type":"llm","modelKey":"a/b","sizeBytes":1073741824},{"type":"embedding","modelKey":"nomic-embed","sizeBytes":1},{"type":"llm"}]'
  It 'returns only language models by default (and skips entries without a key)' {
    $m = @(ConvertFrom-LmsList $json)
    $m.Count | Should Be 1
    $m[0].modelKey | Should Be 'a/b'
  }
  It 'returns every type for an empty type' { @(ConvertFrom-LmsList $json '').Count | Should Be 2 }
  It 'returns nothing for empty output' { @(ConvertFrom-LmsList '').Count | Should Be 0 }
}

Describe 'Get-TomlWithoutListItem' {
  $toml = "tools = [`r`n  `"web_search`",`r`n  `"hue_set`",`r`n  `"tado_heating`"`r`n]`r`nother = 1"
  It 'removes the named entries and keeps the others' {
    $r = Get-TomlWithoutListItem $toml @('hue_set', 'tado_heating')
    $r | Should Match '"web_search"'
    $r | Should Not Match 'hue_set|tado_heating'
    $r | Should Not Match ',\s*\]'
    $r | Should Match 'other = 1'
  }
  It 'does not touch names that only start the same way' { Get-TomlWithoutListItem '["hue_set_extra"]' @('hue_set') | Should Be '["hue_set_extra"]' }
}

Describe 'Merge-SpeechValue' {
  It 'adds a [speech] section when there is none' {
    $r = Merge-SpeechValue "[server]`r`nport = 1" 'model' 'small'
    $r | Should Match '\[speech\]\r\nmodel = "small"'
    $r | Should Match 'port = 1'
  }
  It 'replaces an existing key only inside [speech]' {
    $r = Merge-SpeechValue "[speech]`r`nmodel = `"base`"`r`n[other]`r`nmodel = `"keep`"" 'model' 'large-v3'
    $r | Should Match '\[speech\]\r\nmodel = "large-v3"'
    $r | Should Match '\[other\]\r\nmodel = "keep"'
  }
  It 'adds a missing key to the [speech] section' {
    $r = Merge-SpeechValue "[speech]`r`nmodel = `"base`"`r`n" 'device' 'cuda'
    (Get-SpeechBlock $r).Groups[1].Value | Should Match 'device = "cuda"'
  }
  It 'writes a dollar sign literally' { Merge-SpeechValue "[speech]`r`nvoice_id = `"x`"" 'voice_id' 'C:/a$1b' | Should Match 'voice_id = "C:/a\$1b"' }
}

Describe 'Get-VoiceRecommendation' {
  It 'big NVIDIA card next to the big model: large-v3 on the card and Chatterbox' {
    $r = Get-VoiceRecommendation ([pscustomobject]@{ Vram = 32; Ram = 64; Nvidia = $true; Arm = $false }) 14.6
    $r.Whisper | Should Be 'large-v3'; $r.Device | Should Be 'cuda'; $r.Tts | Should Be 'chatterbox'
  }
  It '12 GB card next to the medium model: small on the card, Kokoro' {
    $r = Get-VoiceRecommendation ([pscustomobject]@{ Vram = 12; Ram = 32; Nvidia = $true; Arm = $false }) 6.7
    $r.Whisper | Should Be 'small'; $r.Device | Should Be 'cuda'; $r.Tts | Should Be 'kokoro'
  }
  It 'no NVIDIA card: processor, int8, Kokoro; base under 16 GB RAM, small above' {
    $r = Get-VoiceRecommendation ([pscustomobject]@{ Vram = 0; Ram = 8; Nvidia = $false; Arm = $false }) -1
    $r.Whisper | Should Be 'base'; $r.Device | Should Be 'cpu'; $r.Compute | Should Be 'int8'; $r.Tts | Should Be 'kokoro'
    (Get-VoiceRecommendation ([pscustomobject]@{ Vram = 0; Ram = 32; Nvidia = $false; Arm = $false }) -1).Whisper | Should Be 'small'
  }
  It 'ARM PC: the light size' { (Get-VoiceRecommendation ([pscustomobject]@{ Vram = 0; Ram = 32; Nvidia = $false; Arm = $true }) -1).Whisper | Should Be 'base' }
  It 'guesses the language model size from the card when it is not given' {
    (Get-VoiceRecommendation ([pscustomobject]@{ Vram = 24; Ram = 64; Nvidia = $true; Arm = $false }) -1).Free | Should Be 7.9
  }
  It 'only recommends sizes and voices from the shared lists' {
    $r = Get-VoiceRecommendation ([pscustomobject]@{ Vram = 16; Ram = 32; Nvidia = $true; Arm = $false }) 6.7
    ($JarvisWhisperIds -contains $r.Whisper) | Should Be $true
    ($JarvisVoiceBackends -contains $r.Tts) | Should Be $true
  }
}

Describe 'Test-JarvisProjectFolder (guard of the uninstaller)' {
  $dir = Join-Path $env:TEMP ('jarvis-guard-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force (Join-Path $dir 'src\openjarvis') | Out-Null
  It 'refuses a folder without start-jarvis.ps1' { (Test-JarvisProjectFolder $dir) | Should Be $false }
  It 'accepts the project folder' {
    Set-Content (Join-Path $dir 'start-jarvis.ps1') '#'
    (Test-JarvisProjectFolder $dir) | Should Be $true
  }
  It 'refuses short paths, empty paths and the user folder' {
    (Test-JarvisProjectFolder 'C:\') | Should Be $false
    (Test-JarvisProjectFolder '') | Should Be $false
    (Test-JarvisProjectFolder $env:USERPROFILE) | Should Be $false
  }
  Remove-Item $dir -Recurse -Force
}

Describe 'Write-WizardLine' {
  $f = Join-Path $env:TEMP ('jarvis-status-' + [guid]::NewGuid().ToString('N') + '.txt')
  It 'appends one line per call' {
    Write-WizardLine $f 'STEP 1|a'; Write-WizardLine $f 'DONE|b'
    @(Get-Content $f) -join ',' | Should Be 'STEP 1|a,DONE|b'
  }
  It 'does nothing without a file' { { Write-WizardLine '' 'x' } | Should Not Throw }
  Remove-Item $f -ErrorAction SilentlyContinue
}
