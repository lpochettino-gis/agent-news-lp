$ErrorActionPreference = "Stop"

Unregister-ScheduledTask -TaskName "Agent News" -Confirm:$false
Write-Host "Tarea eliminada: Agent News"
