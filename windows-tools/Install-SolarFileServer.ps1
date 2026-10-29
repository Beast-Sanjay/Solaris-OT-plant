# Run in elevated PowerShell on win-server, AFTER joining CORP.OTLAB.TEST.
# Installs the Windows File Server role and creates a real SMB document exchange.
# Windows Server license and supplied ISO are required. Not executed automatically by Docker.
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
if (-not (Get-CimInstance Win32_ComputerSystem).PartOfDomain) { throw 'Join CORP.OTLAB.TEST before running this.' }
if ((Get-CimInstance Win32_ComputerSystem).Domain -ine 'corp.otlab.test') { throw 'Incorrect domain.' }
Install-WindowsFeature -Name FS-FileServer -IncludeManagementTools | Out-Null
$root='C:\Solaris\MaintenanceReports'; New-Item -ItemType Directory -Force $root | Out-Null
$share=Get-SmbShare -Name 'SolarMaintenance' -ErrorAction SilentlyContinue
if (-not $share) {
    New-SmbShare -Name SolarMaintenance -Path $root -Description 'SOLARIS ONE corporate maintenance reports' -FullAccess 'CORP\Domain Admins' -ChangeAccess 'CORP\Domain Users' | Out-Null
}
Write-Host 'File server ready at \\SOLAR-FILE01\SolarMaintenance' -ForegroundColor Green
Write-Host 'Verify: Get-SmbShare SolarMaintenance; Test-Path \\SOLAR-FILE01\SolarMaintenance'
