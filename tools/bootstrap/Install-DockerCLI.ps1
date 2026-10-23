. (Join-Path $PSScriptRoot 'Common.ps1')
$catalog='https://download.docker.com/win/static/stable/x86_64/'
$page=(Invoke-WebRequest -Uri $catalog -TimeoutSec 45).Content
$version=[regex]::Matches($page,'docker-(\d+\.\d+\.\d+)\.zip') | ForEach-Object { $_.Groups[1].Value } | Sort-Object {[version]$_} -Descending -Unique | Select-Object -First 1
if(!$version) { throw 'Official Docker Windows CLI archive unavailable.' }
$zip=Join-Path $environmentRoot "downloads\docker-cli-$version.zip"
Get-Download ($catalog+"docker-$version.zip") $zip
$cli=Join-Path $environmentRoot 'runtimes\docker-cli'
if(!(Test-Path -LiteralPath (Join-Path $cli 'docker\docker.exe'))) { Expand-Archive -LiteralPath $zip -DestinationPath $cli -Force }
$docker=Join-Path $cli 'docker\docker.exe'
$compose=Invoke-RestMethod -Uri 'https://api.github.com/repos/docker/compose/releases/latest' -Headers @{'User-Agent'='Match-Trajectory-environment-setup'} -TimeoutSec 45
$asset=$compose.assets | Where-Object name -eq 'docker-compose-windows-x86_64.exe' | Select-Object -First 1
if(!$asset) { throw 'Official Windows Docker Compose binary unavailable.' }
$plugins=Join-Path $environmentRoot 'docker-config\cli-plugins'
$composeExe=Join-Path $plugins 'docker-compose.exe'
Get-Download $asset.browser_download_url $composeExe
Save-Paths @{docker=$docker;dockerPlugins=$plugins;composeVersion=$compose.tag_name;dockerCliVersion=$version}
& $docker --version
& $docker compose version
if($LASTEXITCODE -ne 0) { throw 'Docker Compose client smoke test failed.' }
Write-Output 'DOCKER_CLIENT_COMPLETE_ENGINE_NOT_CONFIGURED'
