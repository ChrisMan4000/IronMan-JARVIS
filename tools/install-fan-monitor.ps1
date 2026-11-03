# IronMan J.A.R.V.I.S.: installs the fan monitor for the HUD (LibreHardwareMonitor, free, MPL-2.0, https://github.com/LibreHardwareMonitor/LibreHardwareMonitor).
# Started by install-jarvis.ps1 with administrator rights (Windows asks once). What it does:
#  1. downloads LibreHardwareMonitor (the release pinned in $LhmVersion below) from GitHub, checks the zip's SHA256 hash and unpacks it into C:\Program Files\LibreHardwareMonitor
#     (a pinned release: it runs with administrator rights, so only this exact file is accepted; to update, change version and hash below)
#  2. writes its settings file with "Remote Web Server" on (port 8085) and "Run On Windows Startup" off (only when no settings file exists yet)
#  3. runs tools\setup-fan-monitor.ps1 (hidden start/stop together with Jarvis, firewall rule that blocks port 8085 from the network)
#  4. starts it once and checks that http://127.0.0.1:8085/data.json answers
# The result is written to -ResultFile: OK, NOWEB (installed, web server silent) or FAIL|<reason>. Exit code 0 for OK/NOWEB, 1 for FAIL.
# Honest note: not tested on a freshly wiped PC.
param([string]$Folder = 'C:\Program Files\LibreHardwareMonitor', [string]$ResultFile = '')
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$LhmVersion = 'v0.9.6'
$LhmZipUrl = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/$LhmVersion/LibreHardwareMonitor.zip"
$LhmZipSha256 = '086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'   # from the GitHub release page of v0.9.6
$resultPath = $ResultFile
function Write-FanResult([string]$Result) {
  Write-Host $Result
  if ($resultPath) { try { [System.IO.File]::WriteAllText($resultPath, $Result) } catch { Write-JarvisLog "fan monitor result file not writable: $($_.Exception.Message)" } }
}
if (-not (Test-IsAdministrator)) { Write-FanResult 'FAIL|not started as administrator'; exit 1 }
try {
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $exe = Join-Path $Folder 'LibreHardwareMonitor.exe'
  if (-not (Test-Path $exe)) {
    $tmp = Join-Path $env:TEMP ('lhm-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $zip = Join-Path $tmp 'lhm.zip'
    Invoke-WebRequest $LhmZipUrl -OutFile $zip -TimeoutSec 300 -UseBasicParsing
    if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $LhmZipSha256) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue; Write-FanResult 'FAIL|downloaded file does not match the known hash'; exit 1 }
    Expand-Archive $zip (Join-Path $tmp 'x') -Force
    $found = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'LibreHardwareMonitor.exe' | Select-Object -First 1
    if (-not $found) { Write-FanResult 'FAIL|LibreHardwareMonitor.exe not in the zip'; exit 1 }
    New-Item -ItemType Directory -Force $Folder | Out-Null
    Copy-Item (Join-Path $found.DirectoryName '*') $Folder -Recurse -Force
    Get-ChildItem $Folder -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    # marker: tells remove-windows-parts.ps1 (used by both uninstallers) that this copy came from our installer, so it may delete it
    [System.IO.File]::WriteAllText((Join-Path $Folder 'installed-by-ironman-jarvis.txt'), "Installed by the IronMan J.A.R.V.I.S. installer ($LhmVersion). Safe to remove with it.")
  }
  if (-not (Test-Path $exe)) { Write-FanResult 'FAIL|LibreHardwareMonitor.exe missing'; exit 1 }
  $cfg = Join-Path $Folder 'LibreHardwareMonitor.config'
  if (-not (Test-Path $cfg)) {
    $x = @'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <appSettings>
    <add key="runWebServerMenuItem" value="true" />
    <add key="listenerPort" value="8085" />
    <add key="startMinMenuItem" value="true" />
    <add key="minTrayMenuItem" value="true" />
  </appSettings>
</configuration>
'@
    [System.IO.File]::WriteAllText($cfg, $x, (New-Object System.Text.UTF8Encoding($false)))
  }
  & (Join-Path $PSScriptRoot 'setup-fan-monitor.ps1') -Folder $Folder
  if ($LASTEXITCODE -ne 0) { Write-FanResult 'FAIL|the scheduled task or the firewall rule could not be created (setup-fan-monitor.ps1)'; exit 1 }
  # check: start it once and wait for the web server
  Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Process $exe -WindowStyle Hidden
  $answered = $false
  for ($i = 0; $i -lt 15 -and -not $answered; $i++) {
    Start-Sleep -Seconds 2
    try { Invoke-RestMethod 'http://127.0.0.1:8085/data.json' -TimeoutSec 3 | Out-Null; $answered = $true } catch { $lastError = $_.Exception.Message }
  }
  Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
  if ($answered) { Write-FanResult 'OK' } else { Write-JarvisLog "fan monitor web server did not answer: $lastError"; Write-FanResult 'NOWEB' }
  exit 0
} catch { Write-FanResult ('FAIL|' + ($_.Exception.Message -replace '[\r\n|]', ' ')); exit 1 }
