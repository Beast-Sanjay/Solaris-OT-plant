# Run interactively inside a domain-joined Windows 11 guest, not on Docker host.
param([ValidateSet('IT','OT')][string]$Role='IT')
$ErrorActionPreference='Stop'
$target=Join-Path $env:USERPROFILE 'Desktop'
if ($Role -eq 'IT') {
 $uri='http://10.0.0.31:8080'
 $script='Get-SolarMaintenance.ps1'
 $name='Solar Enterprise Maintenance'
} else {
 $uri='http://172.18.10.31:8080'
 $script='Get-SolarEngineeringSnapshot.ps1'
 $name='Solar Engineering SCADA Read Only'
}
$w=New-Object -ComObject WScript.Shell
$link=$w.CreateShortcut((Join-Path $target "$name.url"));$link.TargetPath=$uri;$link.Save()
Write-Host "Created $name desktop shortcut. To capture reports, run: powershell -ExecutionPolicy Bypass -File Z:\$script" -ForegroundColor Green
