# Remove the Polyamide Index monthly scheduled task.
#   powershell -ExecutionPolicy Bypass -File unregister_schedule.ps1
$ErrorActionPreference = "Stop"
$task = "PolyamideIndexMonthly"
schtasks /Delete /TN $task /F
if ($LASTEXITCODE -eq 0) { Write-Host "Deleted '$task'." }
else { Write-Warning "Delete failed (exit $LASTEXITCODE). Task may not exist, or you need an elevated shell for a SYSTEM task." }
