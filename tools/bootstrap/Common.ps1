$ErrorActionPreference='Stop'
$environmentRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workspaceRoot=Split-Path $environmentRoot -Parent
$repo=if($env:MATCH_TRAJECTORY_PROJECT_ROOT) { [IO.Path]::GetFullPath($env:MATCH_TRAJECTORY_PROJECT_ROOT) } else { Join-Path $workspaceRoot 'Match-Trajectory' }
function Get-Download([string]$Url,[string]$Destination,[string]$Sha256='') {
    if(Test-Path -LiteralPath $Destination) {
        if(!$Sha256 -or (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Sha256) { return }
    }
    if([IO.Path]::GetFileName($Destination) -eq 'Docker-Desktop-Installer.exe') {
        & (Join-Path $PSScriptRoot 'Install-Ranged.ps1') -Kind Docker
        if($LASTEXITCODE -ne 0) { throw 'Verified ranged Docker download failed.' }
        return
    }
    New-Item -ItemType Directory -Path (Split-Path $Destination -Parent) -Force | Out-Null
    Write-Output ('Downloading '+[IO.Path]::GetFileName($Destination))
    & curl.exe -4 --fail --location --retry 2 --connect-timeout 20 --speed-time 60 --speed-limit 1024 --max-time 900 --silent --show-error --output ($Destination+'.partial') $Url
    if($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
    if($Sha256 -and (Get-FileHash -LiteralPath ($Destination+'.partial') -Algorithm SHA256).Hash -ne $Sha256) { throw "Checksum mismatch: $Destination" }
    Move-Item -LiteralPath ($Destination+'.partial') -Destination $Destination -Force
}
function Save-Paths($Values) {
    $mutex=[Threading.Mutex]::new($false,'Local\MatchTrajectoryEnvironmentPaths')
    if(!$mutex.WaitOne(30000)) { throw 'Cannot acquire environment manifest lock.' }
    try {
    $pathFile=Join-Path $environmentRoot 'manifests\paths.json'
    $all=@{}
    if(Test-Path -LiteralPath $pathFile) { $all=Get-Content -LiteralPath $pathFile -Raw | ConvertFrom-Json -AsHashtable }
    foreach($item in $Values.GetEnumerator()) { $all[$item.Key]=$item.Value }
    $all | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $pathFile -Encoding utf8
    } finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
}
function Load-Paths {
    $script:paths=Get-Content -LiteralPath (Join-Path $environmentRoot 'manifests\paths.json') -Raw | ConvertFrom-Json -AsHashtable
    if($paths.node) { $env:PATH=$paths.node+';'+$env:PATH }
    if($paths.uv) { $env:PATH=(Split-Path $paths.uv -Parent)+';'+$env:PATH }
    if($paths.python) { $env:PATH=(Split-Path $paths.python -Parent)+';'+$env:PATH }
    if($paths.tesseract) { $env:PATH=(Split-Path $paths.tesseract -Parent)+';'+$env:PATH }
    if($paths.tessdata) { $env:TESSDATA_PREFIX=$paths.tessdata }
}
