param(
  [string]$Repo = "mainadwitiya/usagedash"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "uv is required on Windows. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
}

uv tool install --upgrade "git+https://github.com/$Repo.git"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c usagedash tray run"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "UsageDashTray" -Action $action -Trigger $trigger -Force | Out-Null

Write-Host "Tray startup task created: UsageDashTray"
