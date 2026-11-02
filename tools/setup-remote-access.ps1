# Optional: use the Jarvis HUD from your phone or another PC in your HOME network (HTTPS + password).
# Run from the project folder in a NORMAL Windows PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\tools\setup-remote-access.ps1
# It: installs mkcert, makes a certificate for this PC, asks for a password, opens port 8443 for the home network only
# (one UAC prompt) and copies the public certificate (jarvis-ca.crt) to your Desktop for the iPhone.
# Run it again any time; finished parts are skipped. Never share key.pem, auth.json or mkcert's rootCA-key.pem.
$ErrorActionPreference = 'Continue'
$Repo = Split-Path -Parent $PSScriptRoot
$G = Join-Path $env:USERPROFILE '.openjarvis\gateway'
New-Item -ItemType Directory -Force $G | Out-Null

# 1. this PC's home-network address
$ip = (Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress
if (-not $ip) { Write-Host "No home-network address found. Connect to your Wi-Fi or cable and run this again." -ForegroundColor Red; exit 1 }
Write-Host "This PC's address: $ip"

# 2. mkcert
$mk = (Get-Command mkcert -ErrorAction SilentlyContinue).Source
if (-not $mk) {
  winget install --id FiloSottile.mkcert -e --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  $mk = (Get-Command mkcert -ErrorAction SilentlyContinue).Source
  if (-not $mk) { $mk = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter mkcert.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName }
}
if (-not $mk) { Write-Host "mkcert was not found. Close this window, open a NEW PowerShell and run the script again." -ForegroundColor Yellow; exit 1 }

# 3. certificate
& $mk -install
if (-not (Test-Path "$G\cert.pem")) {
  & $mk -cert-file "$G\cert.pem" -key-file "$G\key.pem" $ip localhost 127.0.0.1
  if ($LASTEXITCODE -ne 0) { Write-Host "Certificate could not be created." -ForegroundColor Red; exit 1 }
} else { Write-Host "Certificate already exists (delete cert.pem and key.pem in $G to make a new one, e.g. after your PC's address changed)." }

# 4. password (typed in the next lines, never shown)
if (-not (Test-Path "$G\auth.json")) {
  Set-Location $Repo
  uv run --no-sync python tools\gateway.py --set-password
} else { Write-Host "Password already set. To change it: uv run --no-sync python tools\gateway.py --set-password" }

# 5. firewall: this port, home network only (needs administrator once)
$rule = netsh advfirewall firewall show rule name="Jarvis Gateway 8443 LAN" 2>$null | Out-String
if ($rule -notmatch 'Jarvis Gateway') {
  Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command','netsh advfirewall firewall add rule name="Jarvis Gateway 8443 LAN" dir=in action=allow protocol=TCP localport=8443 remoteip=localsubnet profile=private'
}

# 6. public certificate for the iPhone (the key file is NOT copied)
$caRoot = (& $mk -CAROOT); $desk = [Environment]::GetFolderPath('Desktop')
if (Test-Path "$caRoot\rootCA.pem") { Copy-Item "$caRoot\rootCA.pem" "$desk\jarvis-ca.crt" -Force; Write-Host "Copied jarvis-ca.crt to your Desktop (public file)." }

Write-Host ""
Write-Host "DONE. Start Jarvis as usual (the gateway starts with it), then open:  https://${ip}:8443/hud.html" -ForegroundColor Green
Write-Host "iPhone: send jarvis-ca.crt to it (AirDrop/mail), install the profile, then Settings > General > About > Certificate Trust Settings > switch it on."
Write-Host "iOS Firefox also needs Settings > Firefox > Local Network. Your Wi-Fi network must be set to 'Private' in Windows."
Write-Host "Fullscreen on the iPhone: open the address above, tap the green + button at the top right (or Share > Add to Home Screen) and start Jarvis from the new JARVIS icon."
