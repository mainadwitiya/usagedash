param(
  [string]$Repo = "adwitiya24/usagedash",
  [string]$Version = "latest",
  [switch]$RegisterStartup = $true
)

$ErrorActionPreference = "Stop"

$baseDir = Join-Path $env:LOCALAPPDATA "UsageDash"
New-Item -ItemType Directory -Force -Path $baseDir | Out-Null

if ($Version -eq "latest") {
  $url = "https://github.com/$Repo/releases/latest/download/usagedash-tray-windows-x86_64.exe"
} else {
  $url = "https://github.com/$Repo/releases/download/$Version/usagedash-tray-windows-x86_64.exe"
}

$exe = Join-Path $baseDir "usagedash-tray.exe"
Invoke-WebRequest -Uri $url -OutFile $exe

if ($RegisterStartup) {
  $action = New-ScheduledTaskAction -Execute $exe
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  Register-ScheduledTask -TaskName "UsageDashTray" -Action $action -Trigger $trigger -Force | Out-Null
}

Write-Host "Installed tray app to $exe"
if ($RegisterStartup) {
  Write-Host "Registered startup task: UsageDashTray"
}
