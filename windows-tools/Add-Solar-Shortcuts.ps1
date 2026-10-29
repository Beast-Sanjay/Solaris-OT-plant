[CmdletBinding()]
param([ValidateSet('Corporate','OT')][string]$Zone='Corporate')
$desktop=[Environment]::GetFolderPath('Desktop')
$sites= if($Zone -eq 'Corporate') {
  @(@('Solar Work Orders','http://10.0.0.31:8080'),
    @('AD Authenticated Historian','http://10.0.0.30:8080/api/devices/latest'))
} else {
  @(@('Solar SCADA (Read Only)','http://172.18.10.31:8080'))
}
foreach($site in $sites) {
  $path=Join-Path $desktop ($site[0]+'.url')
  Set-Content -Path $path -Value "[InternetShortcut]`r`nURL=$($site[1])" -Encoding ASCII
  Write-Host "[OK] $path"
}
