# OT Windows 11: poll read-only Level 3 solar SCADA conduit and keep operational log.
# No controller write access is provided to the Windows workstation.
param([string]$Scada='http://172.18.10.31:8080', [int]$Samples=12, [int]$Seconds=5)
$ErrorActionPreference='Stop'
$folder="$env:USERPROFILE\Documents\Solaris-Engineering";New-Item -ItemType Directory -Force $folder|Out-Null
$file=Join-Path $folder ("engineering-snapshot-{0}.csv" -f (Get-Date -Format 'yyyyMMdd-HHmm'))
1..$Samples|ForEach-Object {
 $plant=Invoke-RestMethod "$Scada/api/state" -TimeoutSec 10
 [pscustomobject]@{Time=(Get-Date -Format 'o');PPC='PPC-01';Generation_kW=$plant.generation_kw;Export_kW=$plant.export_kw;
   HealthyInverters=$plant.online_inverters;TransformerWinding_C=$plant.transformer.winding_c;
   RelayTrip=$plant.protection_relay.trip_latched;GridLimit_pct=$plant.grid_limit_pct;
   FeederClosed=$plant.feeder.breaker_closed;AlarmCount=$plant.alarm_count}|Export-Csv -Path $file -NoTypeInformation -Append
 Start-Sleep -Seconds $Seconds
}
Write-Host "Saved read-only plant engineering telemetry to $file" -ForegroundColor Green
