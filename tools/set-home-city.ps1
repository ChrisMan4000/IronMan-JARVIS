# Sets the home city of the HUD: the ATMOSPHERICS weather and the home point on the world map.
# Looks the city up with the free Open-Meteo geocoding service (https://open-meteo.com/en/docs/geocoding-api)
# and writes frontend\public\hud-home.js (this PC only, never in git). Without it the HUD shows London.
# Change the city any time:
#   powershell -ExecutionPolicy Bypass -File tools\set-home-city.ps1 -City "Berlin"
# Exit codes: 0 done or skipped, 1 city not found / no internet (the HUD keeps its current city).
param(
  [string]$City = '',
  [switch]$NoAsk   # the installer wizard already asked: never prompt
)
. (Join-Path $PSScriptRoot 'jarvis-common.ps1')
$Repo = Split-Path $PSScriptRoot -Parent
$Out = Join-Path $Repo 'frontend\public\hud-home.js'
$Saved = Join-Path $env:USERPROFILE '.openjarvis\home-city.txt'   # remembered for the next install (pre-filled answer)

$City = ($City -replace '["<>]', '').Trim()
if (-not $City -and -not (Test-Path $Out) -and (Test-Path $Saved)) { try { $City = ((Get-Content $Saved -Raw -Encoding UTF8) -replace '["<>]', '').Trim() } catch { $City = '' } }   # reinstall: the city of the last install
if (-not $City -and -not $NoAsk) { $City = ((Read-Host 'Which city do you live in? (weather in the HUD; Enter to skip)') -replace '["<>]', '').Trim() }
if (-not $City) {
  if (Test-Path $Out) { Write-Host '  No city given: the HUD keeps its current city.' } else { Write-Host '  No city given: the HUD shows London until you run tools\set-home-city.ps1.' }
  exit 0
}
$hit = $null
try {
  $q = [uri]::EscapeDataString($City)
  $r = Invoke-RestMethod "https://geocoding-api.open-meteo.com/v1/search?name=$q&count=1&language=en&format=json" -TimeoutSec 20
  if ($r -and $r.results) { $hit = @($r.results)[0] }
} catch { Write-JarvisLog "set-home-city: lookup of '$City' failed: $($_.Exception.Message)" }
if (-not $hit) {
  Write-Host "  City '$City' not found (or no internet). The HUD keeps its current city; try again with tools\set-home-city.ps1." -ForegroundColor Yellow
  exit 1
}
$inv = [Globalization.CultureInfo]::InvariantCulture
$name = ([string]$hit.name) -replace '[\\"]', ''
$lat = ([math]::Round([double]$hit.latitude, 3)).ToString($inv)
$lon = ([math]::Round([double]$hit.longitude, 3)).ToString($inv)
$tz = ([string]$hit.timezone) -replace '[^A-Za-z0-9_/+-]', ''
if (-not $tz) { $tz = 'UTC' }
$js = "/* Home city of the HUD (ATMOSPHERICS weather, world-map home point). Written by tools\set-home-city.ps1; this PC only. */`r`n" +
      "window.HOME_CFG={name:`"$name`",lat:$lat,lon:$lon,tz:`"$tz`"};`r`n"
$utf8 = New-Object Text.UTF8Encoding $false
[IO.File]::WriteAllText($Out, $js, $utf8)
try { New-Item -ItemType Directory -Force (Split-Path $Saved) | Out-Null; [IO.File]::WriteAllText($Saved, $City, $utf8) } catch { Write-JarvisLog "set-home-city: $Saved not writable: $($_.Exception.Message)" }
$where = @($hit.admin1, $hit.country) | Where-Object { $_ }
Write-Host ("  Home city: {0} ({1}), {2}, {3}, time zone {4}. Reload the HUD (Ctrl+F5) to see it." -f $name, ($where -join ', '), $lat, $lon, $tz) -ForegroundColor Green
exit 0
