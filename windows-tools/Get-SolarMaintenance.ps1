# Corporate Windows 11: export actual PostgreSQL portal work orders to CSV.
# Only contacts L4 corporate service. Optional SMB export to Windows member server.
param([string]$Portal='http://10.0.0.31:8080', [string]$Share='\\SOLAR-FILE01\SolarMaintenance')
$ErrorActionPreference='Stop'
$orders=(Invoke-RestMethod -Uri "$Portal/api/workorders" -TimeoutSec 15).orders
$local="$env:USERPROFILE\Documents\Solaris";New-Item -ItemType Directory -Force -Path $local|Out-Null
$path=Join-Path $local ("maintenance-{0}.csv" -f (Get-Date -Format 'yyyyMMdd-HHmm'))
$orders|Select-Object reference,title,status,created_at|Export-Csv -NoTypeInformation -Path $path -Encoding UTF8
Write-Host "Exported $($orders.Count) work orders to $path"
if (Test-Path $Share) {Copy-Item -Path $path -Destination $Share -ErrorAction Stop;Write-Host "Published to $Share"}
else {Write-Warning 'Corporate SMB share not reachable. Kept local report; run Install-SolarFileServer.ps1 on win-server.'}
