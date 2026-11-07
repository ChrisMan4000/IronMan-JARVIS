# Shared helpers for the IronMan J.A.R.V.I.S. PowerShell scripts. Dot-source it; it only defines constants and functions.
#   . (Join-Path $PSScriptRoot 'jarvis-common.ps1')            from tools\
#   . (Join-Path $PSScriptRoot 'tools\jarvis-common.ps1')      from the project folder
# The Windows installer wizard copies this file into its temp folder next to list-llms.ps1, voice-rec.ps1 and model-search.ps1.
# Works in Windows PowerShell 5.1 and PowerShell 7. Tests: tests\powershell\jarvis-common.Tests.ps1 (Pester 5).
# All names start with Jarvis so dot-sourcing never overwrites a variable of the calling script; the constants are set with $script:
# because they are meant for that calling script (read them as $JarvisModelTiers etc.).

# A model id ends up inside command lines (lms load, jarvis serve), so only these characters are allowed.
$script:JarvisModelIdPattern = '^[A-Za-z0-9._:/@+-]+$'

# The three language model sizes the installer offers. MinVram: NVIDIA graphics memory (GB) needed for the recommendation.
# Key: the model key LM Studio shows after the download (a Hugging Face repo gets a shorter key).
$script:JarvisModelTiers = @(
  [pscustomobject]@{ Tier = 1; Id = 'lmstudio-community/Qwen3.5-2B-GGUF'; Key = 'qwen3.5-2b';                 Gb = 1.5;  MinVram = 0
                     Note = 'small and fast, for PCs without a graphics card (answers in about 10 s on a Snapdragon laptop)' }
  [pscustomobject]@{ Tier = 2; Id = 'google/gemma-4-12b-qat';             Key = 'google/gemma-4-12b-qat';     Gb = 6.7;  MinVram = 10
                     Note = 'good balance for 12-16 GB graphics cards' }
  [pscustomobject]@{ Tier = 3; Id = 'google/gemma-4-26b-a4b-qat';         Key = 'google/gemma-4-26b-a4b-qat'; Gb = 14.6; MinVram = 22
                     Note = 'best quality, the default (needs about 24 GB or more GPU memory)' }
)

# Everything Jarvis runs: listening ports and the command lines of its programs (stop-jarvis.ps1, services.ps1, the fan watcher).
$script:JarvisServerPort = 8000                              # Jarvis server (own terminal tab, started by start-jarvis.ps1)
$script:JarvisHelperPorts = 5173, 8765, 8766, 8443           # HUD web server, helper, wake word, LAN gateway (run by tools\services.ps1)
$script:JarvisServicePorts = @($JarvisServerPort) + $JarvisHelperPorts
$script:JarvisLmStudioPort = 1234
# command lines of the programs tools\services.ps1 starts, and of the supervisor and the server themselves
$script:JarvisHelperProcessPattern = 'backup-watch\.ps1|hwstats\.py|wake_service\.py|gateway\.py'
$script:JarvisProcessPattern = 'services\.ps1|jarvis serve|' + $JarvisHelperProcessPattern
# Windows user variables the installer can set (the uninstallers remove them, start-jarvis.ps1 reads them again).
$script:JarvisUserEnvVars = 'HUE_BRIDGE_IP', 'SONOS_IP', 'FIRECRAWL_API_KEY', 'OPENJARVIS_WEB_SEARCH_ENGINE', 'SERPLY_API_KEY', 'JARVIS_DOC_ROOT'
# Names of things made in Windows by the optional parts (fan monitor, LAN gateway).
$script:JarvisFanTaskName = 'LibreHardwareMonitor Hidden'
$script:JarvisFanFirewallRule = 'Block LHM 8085 from network'
$script:JarvisGatewayFirewallRule = 'Jarvis Gateway 8443 LAN'

$script:JarvisConfigDir = Join-Path $env:USERPROFILE '.openjarvis'

# Exit codes of all Jarvis scripts: 0 = done (also when an optional part was skipped on purpose), 1 = failed or not done,
# 10 = install-jarvis.ps1 asks to be started again in a fresh process (new programs were installed).

# Whisper sizes for speech recognition (faster-whisper): download GB, rough graphics memory GB (float16).
# The installer wizard gets this list through tools\voice-rec.ps1. Links: https://github.com/SYSTRAN/faster-whisper
$script:JarvisWhisperOptions = @(
  [pscustomobject]@{ Id = 'tiny';     Download = 0.08; Vram = 1;   Note = 'fastest, makes many mistakes' }
  [pscustomobject]@{ Id = 'base';     Download = 0.15; Vram = 1;   Note = 'fine for clear speech on weak PCs' }
  [pscustomobject]@{ Id = 'small';    Download = 0.5;  Vram = 2;   Note = 'good balance' }
  [pscustomobject]@{ Id = 'medium';   Download = 1.5;  Vram = 3.5; Note = 'very accurate' }
  [pscustomobject]@{ Id = 'large-v3'; Download = 3.1;  Vram = 5;   Note = 'most accurate, needs a strong NVIDIA card' }
)
$script:JarvisWhisperIds = @($JarvisWhisperOptions | ForEach-Object { $_.Id })
$script:JarvisVoiceBackends = 'kokoro', 'chatterbox'   # Kokoro: light, any PC. Chatterbox: NVIDIA card, nicer, can copy a voice clip.
$script:JarvisLogFile = Join-Path $JarvisConfigDir 'logs\scripts.log'

function Write-JarvisLog([string]$Message) {
  # Notes a problem the script works around (a failed optional step) in %USERPROFILE%\.openjarvis\logs\scripts.log.
  # Never throws: logging must not break the script that calls it.
  try {
    $dir = Split-Path $JarvisLogFile -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $caller = 'console'; $stack = @(Get-PSCallStack); if ($stack.Count -gt 1 -and $stack[1].ScriptName) { $caller = Split-Path $stack[1].ScriptName -Leaf }
    [System.IO.File]::AppendAllText($JarvisLogFile, ('{0} [{1}] {2}{3}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $caller, $Message, [Environment]::NewLine))
  } catch { Write-Warning "Jarvis log not writable ($JarvisLogFile): $Message" }
}

function Write-WizardLine([string]$Path, [string]$Line) {
  # One line for the Windows installer wizard (status file or result file). No file given: nothing to do.
  if (-not $Path) { return }
  try { [System.IO.File]::AppendAllText($Path, $Line + "`r`n") } catch { Write-JarvisLog "wizard file $Path not writable: $($_.Exception.Message)" }
}

function Read-YesNo([string]$Question) {
  $a = Read-Host "$Question (y/n)"
  return ($a -match '^\s*y')
}

function Test-IsAdministrator {
  return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-ModelId([string]$Id) { return ($Id -match $JarvisModelIdPattern) }

function Test-JarvisProjectFolder([string]$Path) {
  # True only for the project folder itself. Guards the recursive delete in uninstall-jarvis.ps1.
  if (-not $Path -or $Path.Length -le 12) { return $false }   # never a drive root or a short system path
  $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
  if ($full -eq [IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\')) { return $false }
  return ((Test-Path (Join-Path $full 'start-jarvis.ps1')) -and (Test-Path (Join-Path $full 'src\openjarvis')))
}

function Get-TomlWithoutListItem([string]$Text, [string[]]$Names) {
  # Removes "name" entries from the string lists of a TOML file (tools = ["web_search", "hue_set", ...]) and tidies a trailing comma.
  foreach ($n in $Names) { $Text = [regex]::Replace($Text, '\s*"' + [regex]::Escape($n) + '",?', '') }
  return [regex]::Replace($Text, ',(\s*)\]', '$1]')
}

# config.toml [speech] section: used by tools\voice-setup.ps1 (tested in tests\powershell\jarvis-common.Tests.ps1)
function Get-SpeechBlock([string]$text) { return [regex]::Match($text, '(?ms)^\[speech\][ \t]*\r?\n(.*?)(?=^\[|\z)') }
function Merge-SpeechValue([string]$text, [string]$key, [string]$value) {
  $m = Get-SpeechBlock $text
  $line = $key + ' = "' + $value + '"'
  if (-not $m.Success) { return ($text.TrimEnd() + "`r`n`r`n[speech]`r`n" + $line + "`r`n") }
  $g = $m.Groups[1]; $body = $g.Value
  $kre = '(?m)^[ \t]*' + [regex]::Escape($key) + '[ \t]*=[^\r\n]*'
  if ([regex]::IsMatch($body, $kre)) { $body2 = [regex]::Replace($body, $kre, $line.Replace('$', '$$')) }
  else { $body2 = $body.TrimEnd() + "`r`n" + $line + "`r`n`r`n" }
  return ($text.Substring(0, $g.Index) + $body2 + $text.Substring($g.Index + $g.Length))
}

function Test-WakeWordReady([string]$NpuDir) {
  # True when the wake word environment is complete: the installer's marker file, or (setups from before the marker)
  # Python, the openwakeword package and the "hey jarvis" model file.
  if (Test-Path (Join-Path $NpuDir '.venv\jarvis-wake-ready.txt')) { return $true }
  $pkg = Join-Path $NpuDir '.venv\Lib\site-packages\openwakeword'
  return ((Test-Path (Join-Path $NpuDir '.venv\Scripts\python.exe')) -and (Test-Path (Join-Path $pkg '__init__.py')) -and (Test-Path (Join-Path $pkg 'resources\models\hey_jarvis_v0.1.onnx')))
}

function Get-LmStudioApp {
  # Path of the LM Studio app, or $null. A leftover ~\.lmstudio folder of an uninstalled LM Studio does not count.
  $paths = "$env:LOCALAPPDATA\Programs\LM Studio\LM Studio.exe", "$env:ProgramFiles\LM Studio\LM Studio.exe", "${env:ProgramFiles(x86)}\LM Studio\LM Studio.exe"
  return ($paths | Where-Object { Test-Path $_ } | Select-Object -First 1)
}

function Get-LmsCommand {
  # LM Studio's command line tool: 'lms' when it is on PATH, else its default place, else $null (LM Studio not started once yet).
  if (Get-Command lms -ErrorAction SilentlyContinue) { return 'lms' }
  $f = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
  if (Test-Path $f) { return $f }
  return $null
}

function ConvertFrom-LmsList([string]$Json, [string]$Type = 'llm') {
  # The output of 'lms ls --json' as objects (modelKey, sizeBytes, ...), only the given type ('llm', 'embedding'; '' = all).
  # Windows PowerShell 5 returns a JSON array as ONE object, so it is looped over instead of piped.
  $out = @()
  if (-not $Json) { return }
  foreach ($m in (ConvertFrom-Json $Json)) { if ((-not $Type -or $m.type -eq $Type) -and $m.modelKey) { $out += $m } }
  return $out   # callers wrap the call in @( ) to always get a list
}

function Get-LlmModel([string]$Lms, [string]$Type = 'llm') {
  # Models downloaded in LM Studio (see ConvertFrom-LmsList). Empty when lms is missing or fails.
  # Callers wrap the call in @( ) to always get a list.
  if (-not $Lms) { return }
  $json = (& $Lms ls --json 2>$null) -join "`n"
  if ($LASTEXITCODE -ne 0) { Write-JarvisLog "lms ls failed with code $LASTEXITCODE"; return }
  try { return (ConvertFrom-LmsList $json $Type) } catch { Write-JarvisLog "lms ls output not readable: $($_.Exception.Message)" }
}

function Find-NvidiaSmi {
  # nvidia-smi.exe: on PATH, or where the NVIDIA driver puts it (also seen from a 32-bit process such as the installer wizard).
  $c = (Get-Command nvidia-smi -ErrorAction SilentlyContinue).Source
  if ($c) { return $c }
  foreach ($p in "$env:windir\Sysnative\nvidia-smi.exe", "$env:windir\System32\nvidia-smi.exe", "$env:ProgramW6432\NVIDIA Corporation\NVSMI\nvidia-smi.exe") { if (Test-Path $p) { return $p } }
  return $null
}

function Get-HardwareInfo {
  # Vram: NVIDIA graphics memory in GB (0 without NVIDIA card), Ram: GB, Nvidia/Arm: true or false. Read-only.
  $vram = 0
  $smi = Find-NvidiaSmi
  if ($smi) {
    $v = @(& $smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null)[0]   # first card
    if ($LASTEXITCODE -eq 0 -and "$v".Trim() -match '^\d+(\.\d+)?$') { $vram = [math]::Round([double]::Parse("$v".Trim(), [Globalization.CultureInfo]::InvariantCulture) / 1024) }
    else { Write-JarvisLog "nvidia-smi gave no memory size (code $LASTEXITCODE): $v" }
  }
  $ram = 0
  try { $ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) } catch { Write-JarvisLog "RAM size not readable: $($_.Exception.Message)" }
  $arm = ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') -or ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64')
  return [pscustomobject]@{ Vram = $vram; Ram = $ram; Nvidia = ($vram -gt 0); Arm = $arm }
}

function Get-RecommendedModelTier([double]$Vram) {
  # The biggest tier that fits the graphics memory. No NVIDIA card (0 GB): the small model, bigger ones are far too slow on the processor.
  return ($JarvisModelTiers | Where-Object { $Vram -ge $_.MinVram } | Select-Object -Last 1)
}

function Get-VoiceRecommendation($Hardware, [double]$LlmGB = -1) {
  # Whisper size, device and voice for this PC. LlmGB: size of the language model sharing the graphics card (-1 = guess from the card).
  # The memory numbers are rough estimates (measured on an RTX 5090: Whisper large-v3 plus Chatterbox used about 8 GB together).
  if ($LlmGB -lt 0) { $LlmGB = (Get-RecommendedModelTier $Hardware.Vram).Gb }
  # the language model needs its file size plus about 1.5 GB for the context (26B model: file 14.6 GB, measured 15.9 GB)
  $free = [double]$Hardware.Vram - ($LlmGB + 1.5)
  $chatterbox = ($Hardware.Nvidia -and ($free -ge 9))       # Chatterbox about 4 GB + Whisper small or more + safety margin
  $ttsGb = 0; if ($chatterbox) { $ttsGb = 4 }
  $avail = $free - $ttsGb - 1
  $gpuOk = ($Hardware.Nvidia -and ($free -ge 2))
  if ($gpuOk) {
    $fit = @($JarvisWhisperOptions | Where-Object { $_.Id -ne 'tiny' -and $_.Vram -le $avail } | Select-Object -Last 1)
    if ($fit.Count) { $whisper = $fit[0].Id } else { $whisper = 'base' }
    $dev = 'cuda'; $comp = 'float16'
  } else {
    # no usable NVIDIA memory: the processor does the work (int8). ARM and PCs with under 16 GB RAM get the lighter size.
    if ($Hardware.Arm -or ($Hardware.Ram -gt 0 -and $Hardware.Ram -lt 16)) { $whisper = 'base' } else { $whisper = 'small' }
    $dev = 'cpu'; $comp = 'int8'
  }
  $tts = 'kokoro'; if ($chatterbox) { $tts = 'chatterbox' }
  return [pscustomobject]@{ Whisper = $whisper; Device = $dev; Compute = $comp; Tts = $tts; Free = [math]::Round($free, 1); GpuOk = $gpuOk }
}

function Import-JarvisWindowApi {
  # Windows functions to find, minimise and close terminal windows (start-jarvis.ps1, stop-jarvis.ps1): [JarvisWin.User32]::FindWindow(...)
  if ('JarvisWin.User32' -as [type]) { return }
  Add-Type -Namespace JarvisWin -Name User32 -MemberDefinition @'
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string className, string title);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string className, string title);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
[DllImport("user32.dll")] public static extern bool IsWindow(IntPtr window);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
'@
}
function Test-ModelToolCall([string]$Lms, [string]$Key) {
  # loads the model and asks one question that needs a tool; true when the model answers with the tool call
  & $Lms server start 2>&1 | Out-Null   # the chat test needs LM Studio's server (port 1234)
  if ($LASTEXITCODE -ne 0) { Write-JarvisLog "lms server start ended with code $LASTEXITCODE" }
  Start-Sleep -Seconds 3
  & $Lms load $Key -c 4096 -y 2>&1 | Out-Null
  $ok = $false
  try {
    $body = @{ model = $Key; temperature = 0; max_tokens = 200; tool_choice = 'auto'
      messages = @(@{ role = 'user'; content = 'What is the weather in Paris right now? Use the tool.' })
      tools = @(@{ type = 'function'; function = @{ name = 'get_weather'; description = 'Get the current weather of a city'; parameters = @{ type = 'object'; properties = @{ city = @{ type = 'string' } }; required = @('city') } } }) } | ConvertTo-Json -Depth 8
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$JarvisLmStudioPort/v1/chat/completions" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 240
    $ok = [bool]($r.choices[0].message.tool_calls -and "$($r.choices[0].message.tool_calls[0].function.name)" -eq 'get_weather')
  } catch { Write-Host "  Test error: $($_.Exception.Message)" -ForegroundColor Yellow }
  & $Lms unload $Key 2>&1 | Out-Null   # only the tested model: another model that Jarvis uses stays loaded
  return $ok
}

function Get-ModelDownloadState {
  # The state of the background model download (tools\model-download.ps1 writes %USERPROFILE%\.openjarvis\model-download.txt as
  # "<state>|<text>|<process id>|<target>"; state = downloading, testing, loading, done or failed). $null when there is no such file.
  $f = Join-Path $JarvisConfigDir 'model-download.txt'
  if (-not (Test-Path $f)) { return $null }
  $raw = Get-Content $f -Raw -ErrorAction SilentlyContinue
  if (-not $raw) { return $null }
  $p = ($raw -split "`n")[0].Trim() -split '\|'
  if ($p.Count -lt 2) { return $null }
  $alive = $false
  if ($p.Count -ge 3 -and $p[2] -match '^\d+$') { $alive = [bool](Get-Process -Id ([int]$p[2]) -ErrorAction SilentlyContinue) }
  $target = ''; if ($p.Count -ge 4) { $target = $p[3] }
  return [pscustomobject]@{ State = $p[0]; Text = $p[1]; Alive = $alive; Target = $target }
}

function Test-ModelDownloadActive {
  # true while the background model download is still running (it needs LM Studio to stay open)
  $s = Get-ModelDownloadState
  return [bool]($s -and $s.Alive -and $s.State -in 'downloading', 'testing', 'loading')
}
