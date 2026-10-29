# IronMan J.A.R.V.I.S.: installs the fan monitor for the HUD (LibreHardwareMonitor, free, MPL-2.0, https://github.com/LibreHardwareMonitor/LibreHardwareMonitor).
# Started by install-jarvis.ps1 with administrator rights (Windows asks once). What it does:
#  1. downloads the newest LibreHardwareMonitor release zip from GitHub and unpacks it into C:\Program Files\LibreHardwareMonitor
#  2. writes its settings file with "Remote Web Server" on (port 8085) and "Run On Windows Startup" off (only when no settings file exists yet)
#  3. runs tools\setup-fan-monitor.ps1 (hidden start/stop together with Jarvis, firewall rule that blocks port 8085 from the network)
#  4. starts it once and checks that http://127.0.0.1:8085/data.json answers
# The result (OK / NOWEB / FAIL: reason) is written to -ResultFile. Honest note: not tested on a freshly wiped PC.
param([string]$Folder = 'C:\Program Files\LibreHardwareMonitor', [string]$ResultFile = '')
function Done($t) { Write-Host $t; if ($ResultFile) { try { [System.IO.File]::WriteAllText($ResultFile, $t) } catch { } }; exit }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Done 'FAIL: not started as administrator' }
try {
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $exe = Join-Path $Folder 'LibreHardwareMonitor.exe'
  if (-not (Test-Path $exe)) {
    $rel = Invoke-RestMethod 'https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest' -Headers @{ 'User-Agent' = 'IronMan-JARVIS' } -TimeoutSec 60
    $asset = $rel.assets | Where-Object { $_.name -match '^LibreHardwareMonitor\.zip$' } | Select-Object -First 1
    if (-not $asset) { $asset = $rel.assets | Where-Object { $_.name -match '\.zip$' -and $_.name -notmatch 'net472|linux|mac' } | Select-Object -First 1 }
    if (-not $asset -or $asset.browser_download_url -notmatch '^https://github\.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/') { Done 'FAIL: no release zip found' }
    $tmp = Join-Path $env:TEMP ('lhm-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $zip = Join-Path $tmp 'lhm.zip'
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -TimeoutSec 300
    if ((Get-Item $zip).Length -lt 100000) { Done 'FAIL: download too small' }
    Expand-Archive $zip (Join-Path $tmp 'x') -Force
    $found = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'LibreHardwareMonitor.exe' | Select-Object -First 1
    if (-not $found) { Done 'FAIL: LibreHardwareMonitor.exe not in the zip' }
    New-Item -ItemType Directory -Force $Folder | Out-Null
    Copy-Item (Join-Path $found.DirectoryName '*') $Folder -Recurse -Force
    Get-ChildItem $Folder -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    # marker: tells remove-fan-monitor.ps1 (and the uninstaller) that this copy came from our installer, so it may delete it
    [System.IO.File]::WriteAllText((Join-Path $Folder 'installed-by-ironman-jarvis.txt'), 'Installed by the IronMan J.A.R.V.I.S. installer. Safe to remove with it.')
  }
  if (-not (Test-Path $exe)) { Done 'FAIL: LibreHardwareMonitor.exe missing' }
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
  # check: start it once and wait for the web server
  Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Process $exe -WindowStyle Hidden
  $ok = $false
  for ($i = 0; $i -lt 15 -and -not $ok; $i++) {
    Start-Sleep -Seconds 2
    try { Invoke-RestMethod 'http://127.0.0.1:8085/data.json' -TimeoutSec 3 | Out-Null; $ok = $true } catch { }
  }
  Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
  if ($ok) { Done 'OK' } else { Done 'NOWEB' }
} catch { Done ('FAIL: ' + $_.Exception.Message) }
