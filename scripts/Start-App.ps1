param([int]$Port=18765, [switch]$NoBrowser, [switch]$RebuildFrontend, [string]$DataDir='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Enter-DevEnvironment.ps1')
. (Join-Path $PSScriptRoot 'FrontendBuild.ps1')
$env:PYTHONUTF8='1'
$env:MATCH_TRAJECTORY_FONT_PATH=Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'runtimes\fonts\NotoSansCJKsc-Regular.otf'
$distReady=Test-Path -LiteralPath 'web\dist\index.html'
Invoke-FrontendBuildIfNeeded -RebuildFrontend:$RebuildFrontend -DistReady $distReady -Build {
    node node_modules/vite/bin/vite.js build --config web/vite.config.ts
}
$appArguments=@('-m','app.cli','--port',"$Port")
if ($NoBrowser) { $appArguments+='--no-browser' }
if ($DataDir) { $appArguments+=@('--data-dir',$DataDir) }
python @appArguments
exit $LASTEXITCODE
