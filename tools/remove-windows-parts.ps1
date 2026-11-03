# IronMan J.A.R.V.I.S.: removes what the optional parts added to Windows itself. Needs administrator rights (the uninstallers ask Windows for them).
#  - fan monitor (tools\install-fan-monitor.ps1 / setup-fan-monitor.ps1): the scheduled task, the firewall rule that blocks port 8085, and the
#    LibreHardwareMonitor folder - the folder ONLY if it carries the marker file of install-fan-monitor.ps1 (a copy you installed yourself stays)
#  - LAN gateway (tools\setup-remote-access.ps1): the firewall rule that opens port 8443 to the home network
# Exit code 0 when everything is gone, 1 when something is left (the messages say what).
param([string]$Folder = 'C:\Program Files\LibreHardwareMonitor')
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
if (-not (Test-IsAdministrator)) { Write-Host "Please run this as administrator."; exit 1 }
$complete = $true
function Test-FirewallRule([string]$Name) { netsh advfirewall firewall show rule name="$Name" 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }

Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
if (Get-ScheduledTask -TaskName $JarvisFanTaskName -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $JarvisFanTaskName -Confirm:$false -ErrorAction SilentlyContinue
  if (Get-ScheduledTask -TaskName $JarvisFanTaskName -ErrorAction SilentlyContinue) { $complete = $false; Write-Host "Could not remove the scheduled task '$JarvisFanTaskName'." }
  else { Write-Host "Removed the scheduled task '$JarvisFanTaskName'." }
}
foreach ($rule in $JarvisFanFirewallRule, $JarvisGatewayFirewallRule) {
  if (-not (Test-FirewallRule $rule)) { continue }
  netsh advfirewall firewall delete rule name="$rule" | Out-Null
  if (Test-FirewallRule $rule) { $complete = $false; Write-Host "Could not remove the firewall rule '$rule'." }
  else { Write-Host "Removed the firewall rule '$rule'." }
}
$marker = Join-Path $Folder 'installed-by-ironman-jarvis.txt'
if (Test-Path $marker) {
  Start-Sleep -Seconds 1   # LibreHardwareMonitor needs a moment to release its files
  Remove-Item $Folder -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path $Folder) { $complete = $false; Write-Host "Could not remove everything in $Folder (a file is still in use?)." }
  else { Write-Host "Removed $Folder." }
} elseif (Test-Path $Folder) { Write-Host "$Folder was not installed by IronMan J.A.R.V.I.S. (no marker file), so it stays." }
if ($complete) { Write-Host "Done."; exit 0 }
exit 1
