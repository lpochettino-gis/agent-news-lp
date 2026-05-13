$ErrorActionPreference = "Stop"

$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExeRunner = Join-Path $AgentDir "AgentNews.exe"
$CmdRunner = Join-Path $AgentDir "run_agent_news.cmd"
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (Test-Path -LiteralPath $ExeRunner) {
  $Execute = $ExeRunner
  $Argument = ""
  $Runner = $ExeRunner
} elseif (Test-Path -LiteralPath $CmdRunner) {
  $Execute = $env:ComSpec
  $Argument = "/c `"$CmdRunner`""
  $Runner = $CmdRunner
} else {
  throw "No se encontro AgentNews.exe ni run_agent_news.cmd en: $AgentDir"
}

if ($Argument) {
  $Action = New-ScheduledTaskAction `
    -Execute $Execute `
    -Argument $Argument `
    -WorkingDirectory $AgentDir
} else {
  $Action = New-ScheduledTaskAction `
    -Execute $Execute `
    -WorkingDirectory $AgentDir
}

$Trigger = New-ScheduledTaskTrigger -Daily -At 8:30AM

$Settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$Principal = New-ScheduledTaskPrincipal `
  -UserId $Identity `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName "Agent News" `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Principal $Principal `
  -Description "Genera y abre el resumen diario de noticias a las 08:30." `
  -Force | Out-Null

Write-Host "Tarea registrada: Agent News"
Write-Host "Horario: todos los dias a las 08:30"
Write-Host "Ejecutor: $Runner"
