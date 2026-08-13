# Register the Polyamide Index run with Windows Task Scheduler:
# the 20th of EVERY MONTH at 07:00. Runs the full pipeline (build index ->
# dashboard -> email the report to the configured recipients).
#
# UNATTENDED: runs as SYSTEM with highest privileges, whether or not you are
# logged on. MUST be run from an ELEVATED (Run as administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File register_schedule.ps1
#
# To run under YOUR account instead (e.g. if SMTP/network needs your profile),
# pass -CurrentUser (you will be prompted for your password by schtasks):
#   powershell -ExecutionPolicy Bypass -File register_schedule.ps1 -CurrentUser

param([switch]$CurrentUser)

$ErrorActionPreference = "Stop"
$bat  = Join-Path $PSScriptRoot "run_monthly.bat"
$task = "PolyamideIndexMonthly"

if (-not (Test-Path $bat)) { throw "run_monthly.bat not found next to this script" }
Write-Host "runner : $bat"
Write-Host "task   : $task  (MONTHLY, day 20, 07:00)"

# Wrap the runner path in quotes only if it contains a space (schtasks /TR needs
# the whole command quoted when it has spaces; this path normally has none).
$tr = if ($bat -match '\s') { '"' + $bat + '"' } else { $bat }

if ($CurrentUser) {
  # Prompts for your password; runs whether logged on or not, under your profile.
  schtasks /Create /SC MONTHLY /D 20 /ST 07:00 /TN $task /TR $tr /RL HIGHEST /RU $env:USERNAME /IT /F
} else {
  # SYSTEM: no stored password, but requires an elevated shell to create.
  schtasks /Create /SC MONTHLY /D 20 /ST 07:00 /TN $task /TR $tr /RU SYSTEM /RL HIGHEST /F
}

if ($LASTEXITCODE -ne 0) {
  Write-Warning "Create failed (exit $LASTEXITCODE). For the SYSTEM task you must be in an ELEVATED PowerShell (Run as administrator). Or retry with -CurrentUser."
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Registered '$task' - 20th of every month at 07:00. Verify with:"
Write-Host "  schtasks /Query /TN $task /V /FO LIST"
Write-Host "Trigger a real run now (builds AND sends the email) with:"
Write-Host "  schtasks /Run /TN $task"
