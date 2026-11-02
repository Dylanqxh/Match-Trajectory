$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Enter-DevEnvironment.ps1')
$env:PYTHONUTF8='1'
$env:MATCH_TRAJECTORY_FONT_PATH=Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'runtimes\fonts\NotoSansCJKsc-Regular.otf'
$testRunPath=Join-Path (Get-Location) ('artifacts\pytest-'+[guid]::NewGuid().ToString('N'))
python -m pytest -q -p no:cacheprovider --basetemp $testRunPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node node_modules/typescript/bin/tsc --project web/tsconfig.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node node_modules/vite/bin/vite.js build --config web/vite.config.ts
exit $LASTEXITCODE
