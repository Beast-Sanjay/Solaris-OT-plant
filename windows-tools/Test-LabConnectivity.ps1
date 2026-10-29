# Run in Windows PowerShell; works before joining the domain.
[CmdletBinding()]
param([ValidateSet('Corporate','OT')][string]$Zone='Corporate')
$ErrorActionPreference='Stop'
$dns= if($Zone -eq 'Corporate') {'10.0.0.10'} else {'172.18.10.10'}
$realm= if($Zone -eq 'Corporate') {'corp.otlab.test'} else {'ics.otlab.test'}
Write-Host "Testing $Zone DNS and domain connectivity"
Resolve-DnsName -Server $dns -Type SRV "_ldap._tcp.dc._msdcs.$realm" | Out-Host
foreach($p in @(53,88,389,445)) {
  $ok= Test-NetConnection -ComputerName $dns -Port $p -InformationLevel Quiet
  Write-Host "TCP $dns`:$p = $ok"
  if(-not $ok){ throw 'Missing connectivity to a domain controller.' }
}
(Get-CimInstance Win32_ComputerSystem) | Select-Object Name,Domain,PartOfDomain | Format-List
if($Zone -eq 'Corporate') {
  foreach($t in @('http://10.0.0.31:8080/health','http://10.0.0.30:8080/api/devices/latest')) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri $t -TimeoutSec 6
      Write-Host "$t -> $($r.StatusCode)"
    } catch {
      $code = [int]$_.Exception.Response.StatusCode
      if($code -eq 401) { Write-Host "$t -> 401 (correct: corporate AD credentials required)" }
      else { Write-Warning "$t failed: $_" }
    }
  }
} else {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://172.18.10.31:8080/api/state' -TimeoutSec 6
    Write-Host "Read-only Level 2 SCADA via Level 3 conduit -> $($r.StatusCode)"
  } catch { Write-Warning "OT operator view unavailable: $_" }
}
