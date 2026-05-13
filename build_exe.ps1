$ErrorActionPreference = "Stop"

$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $AgentDir
$DistDir = Join-Path $RootDir "agent_news_dist"
$TempRoot = Join-Path $env:TEMP "agent_news_pyinstaller"
$BuildDir = Join-Path $TempRoot "build"
$SpecDir = Join-Path $TempRoot "spec"
$TempDistDir = Join-Path $TempRoot "dist"

function Assert-ChildPath {
  param(
    [Parameter(Mandatory = $true)][string]$Parent,
    [Parameter(Mandatory = $true)][string]$Child
  )
  $ResolvedParent = [IO.Path]::GetFullPath($Parent)
  $ResolvedChild = [IO.Path]::GetFullPath($Child)
  if (-not $ResolvedChild.StartsWith($ResolvedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Ruta invalida: $ResolvedChild"
  }
}

if (Test-Path -LiteralPath $DistDir) {
  Assert-ChildPath -Parent $RootDir -Child $DistDir
  Remove-Item -LiteralPath $DistDir -Recurse -Force
}
New-Item -ItemType Directory -Path $DistDir | Out-Null

if (Test-Path -LiteralPath $TempRoot) {
  Assert-ChildPath -Parent $env:TEMP -Child $TempRoot
  Remove-Item -LiteralPath $TempRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $TempRoot | Out-Null

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name AgentNews `
  --distpath $TempDistDir `
  --workpath $BuildDir `
  --specpath $SpecDir `
  (Join-Path $AgentDir "agent_news.py")

Copy-Item -LiteralPath (Join-Path $TempDistDir "AgentNews.exe") -Destination $DistDir
Copy-Item -LiteralPath (Join-Path $AgentDir "install_agent_news_task.ps1") -Destination $DistDir
Copy-Item -LiteralPath (Join-Path $AgentDir "uninstall_agent_news_task.ps1") -Destination $DistDir
Copy-Item -LiteralPath (Join-Path $AgentDir "instalar_agent_news.cmd") -Destination $DistDir
Copy-Item -LiteralPath (Join-Path $AgentDir "desinstalar_agent_news.cmd") -Destination $DistDir
Copy-Item -LiteralPath (Join-Path $AgentDir "README_AGENT_NEWS_EXE.md") -Destination $DistDir

Write-Host "Paquete creado en: $DistDir"
Write-Host "Ejecutable: $(Join-Path $DistDir 'AgentNews.exe')"
