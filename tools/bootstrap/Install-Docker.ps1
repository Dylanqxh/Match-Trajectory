. (Join-Path $PSScriptRoot 'Common.ps1')
$installer=Join-Path $environmentRoot 'downloads\Docker-Desktop-Installer.exe'
Get-Download 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' $installer
$signature=Get-AuthenticodeSignature -LiteralPath $installer
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Docker') { throw 'Docker installer signature verification failed.' }
$wslOutput=(& wsl.exe --version 2>&1 | Out-String)
$wslCode=$LASTEXITCODE
$system=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,BuildNumber,OSArchitecture
[pscustomobject]@{Installer=$installer;Signature=$signature.Status.ToString();Signer=$signature.SignerCertificate.Subject;WSLExitCode=$wslCode;WSLVersion=$wslOutput;System=$system;EngineInstalled=$false;Reason='Docker Desktop requires Windows/WSL system integration; no global installation performed under the D-drive-only constraint.'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $environmentRoot 'manifests\docker-readiness.json') -Encoding utf8
Save-Paths @{dockerInstaller=$installer;dockerInstallRoot=(Join-Path $environmentRoot 'runtimes\docker-desktop');dockerDataRoot=(Join-Path $environmentRoot 'docker-data')}
Write-Output "DOCKER_INSTALLER_VERIFIED=$installer"
Write-Output "WSL_EXIT_CODE=$wslCode"
exit 0
