$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Enter-DevEnvironment.ps1')
& python (Join-Path $PSScriptRoot '..\tools\verify-environment.py')
if($LASTEXITCODE -ne 0) { throw 'Runtime verification failed. See the environment manifest report.' }
& uv pip check
if($LASTEXITCODE -ne 0) { throw 'Python dependencies have conflicts.' }
& npm.cmd ls --depth=0
if($LASTEXITCODE -ne 0) { throw 'Node dependencies have conflicts.' }
