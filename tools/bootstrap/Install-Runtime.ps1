. (Join-Path $PSScriptRoot 'Common.ps1')
$headers=@{'User-Agent'='Match-Trajectory-environment-setup'}
$releases=Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -TimeoutSec 45
$node=$releases | Where-Object { $_.version -match '^v22\.' } | Select-Object -First 1
if(!$node) { throw 'No Node 22 release found.' }
$nodeName="node-$($node.version)-win-x64.zip"
$nodeUrl="https://nodejs.org/dist/$($node.version)/$nodeName"
$shas=(Invoke-WebRequest -Uri "https://nodejs.org/dist/$($node.version)/SHASUMS256.txt" -TimeoutSec 45).Content
$checksum=($shas -split "`n" | Where-Object { $_ -match ([regex]::Escape($nodeName)+'\s*$') }) -split '\s+' | Select-Object -First 1
if(!$checksum) { throw 'Node archive checksum unavailable.' }
$nodeZip=Join-Path $environmentRoot "downloads\$nodeName"
Get-Download $nodeUrl $nodeZip $checksum
$nodeHome=Join-Path $environmentRoot "runtimes\node-$($node.version)-win-x64"
if(!(Test-Path -LiteralPath (Join-Path $nodeHome 'node.exe'))) { Expand-Archive -LiteralPath $nodeZip -DestinationPath (Join-Path $environmentRoot 'runtimes') -Force }
$env:PATH=$nodeHome+';'+$env:PATH
$uvRelease=Invoke-RestMethod -Uri 'https://api.github.com/repos/astral-sh/uv/releases/latest' -Headers $headers -TimeoutSec 45
$uvAsset=$uvRelease.assets | Where-Object name -eq 'uv-x86_64-pc-windows-msvc.zip' | Select-Object -First 1
if(!$uvAsset) { throw 'uv Windows archive unavailable.' }
$uvZip=Join-Path $environmentRoot "downloads\uv-$($uvRelease.tag_name)-windows.zip"
$uvHash=if($uvAsset.digest -match '^sha256:(.*)$') { $Matches[1] } else { '' }
Get-Download $uvAsset.browser_download_url $uvZip $uvHash
$uvHome=Join-Path $environmentRoot 'runtimes\uv'
if(!(Test-Path -LiteralPath (Join-Path $uvHome 'uv.exe'))) { Expand-Archive -LiteralPath $uvZip -DestinationPath $uvHome -Force }
$uv=(Get-ChildItem -LiteralPath $uvHome -Filter uv.exe -Recurse | Select-Object -First 1).FullName
if(!$uv) { throw 'uv executable missing.' }
& $uv --version
& $uv python install 3.12
if($LASTEXITCODE -ne 0) { throw 'Managed Python installation failed.' }
$python=(& $uv python find 3.12 --managed-python | Select-Object -Last 1).Trim()
if($LASTEXITCODE -ne 0) { throw 'Managed Python lookup failed.' }
Save-Paths @{node=$nodeHome;uv=$uv;python=$python;repository=$repo;nodeVersion=$node.version;uvVersion=$uvRelease.tag_name}
$env:UV_PROJECT_ENVIRONMENT=Join-Path $repo '.venv'
Push-Location $repo
try {
    & $uv lock
    if($LASTEXITCODE -ne 0) { throw 'Python dependency lock failed.' }
    & $uv sync --locked
    if($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    $venvPython=Join-Path $repo '.venv\Scripts\python.exe'
    Save-Paths @{venvPython=$venvPython}
    $playwrightVersion=(& $venvPython -c 'import importlib.metadata; print(importlib.metadata.version("playwright"))').Trim()
    & (Join-Path $nodeHome 'npm.cmd') pkg set "devDependencies.@playwright/test=$playwrightVersion"
    & (Join-Path $nodeHome 'npm.cmd') install --no-fund --no-audit
    if($LASTEXITCODE -ne 0) { throw 'Node dependency installation failed.' }
    & $venvPython -m playwright install chromium
    if($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
    & (Join-Path $nodeHome 'npm.cmd') audit --omit=dev --json | Set-Content -LiteralPath (Join-Path $environmentRoot 'logs\npm-audit.json') -Encoding utf8
} finally { Pop-Location }
Write-Output 'RUNTIME_STAGE_COMPLETE'
