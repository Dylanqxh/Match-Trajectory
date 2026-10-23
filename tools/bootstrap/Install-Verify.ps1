. (Join-Path $PSScriptRoot 'Common.ps1')
. (Join-Path $repo 'scripts\Enter-DevEnvironment.ps1')
& python (Join-Path $repo 'tools\verify-environment.py')
if($LASTEXITCODE -ne 0) { throw 'Runtime smoke verification has failures.' }
& uv pip check
if($LASTEXITCODE -ne 0) { throw 'Python dependency integrity check failed.' }
& npm.cmd ls --depth=0
if($LASTEXITCODE -ne 0) { throw 'Node dependency integrity check failed.' }
