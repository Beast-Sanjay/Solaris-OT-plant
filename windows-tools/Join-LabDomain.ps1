# Run as an elevated PowerShell session INSIDE a dockur Windows guest.
# Example: Set-ExecutionPolicy -Scope Process Bypass -Force
#          & 'Z:\Join-LabDomain.ps1' -Zone Corporate
# No domain passwords or credentials are stored in the package.
[CmdletBinding()]
param([ValidateSet('Corporate','OT')][string]$Zone='Corporate', [switch]$CheckOnly)
$ErrorActionPreference='Stop'
$realm = if($Zone -eq 'Corporate') {'corp.otlab.test'} else {'ics.otlab.test'}
$dns   = if($Zone -eq 'Corporate') {'10.0.0.10'} else {'172.18.10.10'}
$short = if($Zone -eq 'Corporate') {'CORP'} else {'ICS'}
Write-Host "[INFO] Zone=$Zone Domain=$realm DNS=$dns"
$adapter = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.HardwareInterface } | Select-Object -First 1
if (-not $adapter) { $adapter = Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1 }
if (-not $adapter) { throw 'No active Windows guest network adapter detected.' }
Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ServerAddresses $dns
Clear-DnsClientCache
$dnsOk = Resolve-DnsName -Server $dns -Type SRV "_ldap._tcp.dc._msdcs.$realm" -ErrorAction Stop
Write-Host ('[PASS] AD SRV DNS record: '+ (($dnsOk | Where-Object Type -eq 'SRV' | Select-Object -First 1).NameTarget))
foreach($port in @(88,389,445)) {
  if(-not (Test-NetConnection -ComputerName $dns -Port $port -InformationLevel Quiet)) {
    throw "AD controller unreachable at $dns port $port; check Samba/docker networks."
  }
  Write-Host "[PASS] DC TCP $dns`:$port"
}
if($CheckOnly) { Write-Host '[PASS] Connectivity verified (domain join not attempted).'; exit 0 }
$edition = (Get-CimInstance Win32_OperatingSystem).Caption
Write-Host "[INFO] Windows edition: $edition. Windows Home cannot join an AD domain."
$computer = Get-CimInstance Win32_ComputerSystem
if($computer.PartOfDomain) { Write-Host "[INFO] Already joined to $($computer.Domain)"; exit 0 }
$credential = Get-Credential -UserName "$short\Administrator" -Message "Enter the $short lab domain admin password from the Docker host .env"
Add-Computer -DomainName $realm -Credential $credential -Force -Restart -ErrorAction Stop
