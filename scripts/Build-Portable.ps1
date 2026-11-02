param([switch]$SkipChecks, [string]$OutputRoot='dist')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Enter-DevEnvironment.ps1')
$env:PYTHONUTF8='1'
$env:PYINSTALLER_CONFIG_DIR=Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'cache\pyinstaller'
$projectRoot=(Get-Location).Path
$outputCandidate=if ([IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot } else { Join-Path $projectRoot $OutputRoot }
$outputPath=[IO.Path]::GetFullPath($outputCandidate)
if (!$outputPath.StartsWith($projectRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output must stay inside the project workspace'
}
$destination=Join-Path $outputPath 'MatchTrajectory'
if (Test-Path -LiteralPath (Join-Path $destination 'data')) {
    throw 'Portable output contains user data. Choose a different -OutputRoot; existing data will not be deleted.'
}
if (!$SkipChecks) {
    node node_modules/typescript/bin/tsc --project web/tsconfig.json
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed' }
    node node_modules/vite/bin/vite.js build --config web/vite.config.ts
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
}
$fontRoot=Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'runtimes\fonts'
$browserRoot=Join-Path $env:MATCH_TRAJECTORY_ENV_ROOT 'runtimes\playwright'
$font=Join-Path $fontRoot 'NotoSansCJKsc-Regular.otf'
$fontLicense=Join-Path $fontRoot 'LICENSE-NotoSansCJK.txt'
foreach ($required in @('web\dist\index.html',$font,$fontLicense,$browserRoot)) {
    if (!(Test-Path -LiteralPath $required)) { throw "Required build resource missing: $required" }
}
$separator=[IO.Path]::PathSeparator
$webDist=(Resolve-Path -LiteralPath 'web\dist').Path
$entry=(Resolve-Path -LiteralPath 'app\entry.py').Path
$skillRoot=(Resolve-Path -LiteralPath 'skills').Path
$packageArguments=@('--noconfirm','--clean','--onedir','--name','MatchTrajectory',
    '--distpath',$outputPath,'--workpath','build\pyinstaller','--specpath','build','--paths','.',
    '--collect-all','playwright','--collect-all','pypdfium2_raw',
    '--hidden-import','sqlalchemy.dialects.sqlite.pysqlite',
    '--add-data',("${webDist}${separator}web/dist"),
    '--add-data',("${skillRoot}${separator}skills"),
    '--add-data',("${font}${separator}assets/fonts"),
    '--add-data',("${fontLicense}${separator}assets/fonts"),
    '--add-data',("${browserRoot}${separator}runtime-browsers"),$entry)
python -m PyInstaller @packageArguments
if ($LASTEXITCODE -ne 0) { throw 'Portable build failed' }
$buildReport=@{ milestone='M1'; cleanMachineVerified=$false; liveProvidersVerified=0; realModelQualityVerified=$false; redistributionLicenseReviewComplete=$false;
    note='Local portable probe only; not a publicly validated release.'; builtAtUtc=[DateTime]::UtcNow.ToString('o') }
$buildReport | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination 'M1-probe.json') -Encoding utf8
@'
Match-Trajectory M1 本机便携包探针

双击 MatchTrajectory.exe，浏览器会打开本机工作台。关闭服务窗口可停止服务。
默认资料目录为程序旁的 data；也可使用 --data-dir 指定可写目录。
在左下角模型连接中配置 Key，回到首页填写方向和材料，确认发送后生成。
支持候选采用、编辑、重新审阅、草稿与正式 PDF/DOCX 导出。
Key 仅保留在本次服务内存中，重启需重新填写。虚构演示不可直接投递。
此包仍需干净 Windows、完整第三方许可与真实模型验证，尚不是公开发布版。
'@ | Set-Content -LiteralPath (Join-Path $destination '使用说明.txt') -Encoding utf8
Write-Host "Portable probe built: $destination"
