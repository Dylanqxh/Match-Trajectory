param([switch]$DownloadDockerDesktop)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$environmentRoot=Join-Path (Split-Path $projectRoot -Parent) '.dev-environment'
if([IO.Path]::GetPathRoot($environmentRoot) -eq 'C:\') { throw 'This bootstrap requires a non-C drive checkout for runtime storage.' }
$source=Join-Path $projectRoot 'tools\bootstrap'
$target=Join-Path $environmentRoot 'scripts'
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach($name in @('Initialize-Workspace.ps1','Common.ps1','Install-Runtime.ps1','Install-OCR.ps1','Install-Office.ps1','Install-DockerCLI.ps1','Install-Docker.ps1','Install-Ranged.ps1','Install-Verify.ps1')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $target $name) -Force
}
$env:MATCH_TRAJECTORY_PROJECT_ROOT=$projectRoot
foreach($stage in @('Runtime','OCR','Office','DockerCLI')) {
    & (Join-Path $target 'Initialize-Workspace.ps1') -Stage $stage
    if($LASTEXITCODE -ne 0) { throw "Bootstrap stage failed: $stage" }
}
if($DownloadDockerDesktop) { & (Join-Path $target 'Initialize-Workspace.ps1') -Stage Docker }
& (Join-Path $target 'Initialize-Workspace.ps1') -Stage Verify
if($LASTEXITCODE -ne 0) { throw 'Runtime verification failed.' }
