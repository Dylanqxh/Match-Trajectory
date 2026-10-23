param([ValidateSet('Docker','Tesseract')][string]$Kind)
. (Join-Path $PSScriptRoot 'Common.ps1')
function Get-Ranged([string]$Url,[string]$Destination,[long]$Size,[string]$Hash='',[string]$ETag='') {
    if(Test-Path -LiteralPath $Destination) {
        if((Get-Item -LiteralPath $Destination).Length -eq $Size -and (!$Hash -or (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Hash)) { return }
    }
    $chunkRoot=$Destination+'.chunks'
    New-Item -ItemType Directory -Path $chunkRoot -Force | Out-Null
    $chunkSize=8MB
    $count=[int][math]::Ceiling($Size/$chunkSize)
    Write-Output "RANGE_DOWNLOAD=$([IO.Path]::GetFileName($Destination)) PARTS=$count"
    0..($count-1) | ForEach-Object -Parallel {
        $ErrorActionPreference='Stop'
        $index=$_
        $start=[long]$index*$using:chunkSize
        $end=[math]::Min($using:Size-1,$start+$using:chunkSize-1)
        $part=Join-Path $using:chunkRoot ('part-'+$index.ToString('D4'))
        $expected=$end-$start+1
        if((Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -eq $expected) { return }
        $arguments=@('-4','--fail','--location','--retry','3','--retry-all-errors','--retry-delay','2','--connect-timeout','15','--speed-time','45','--speed-limit','1024','--max-time','180','--range',"$start-$end",'--silent','--show-error','--output',($part+'.partial'),'--write-out','%{http_code}')
        if($using:ETag) { $arguments+=@('--header',('If-Match: '+$using:ETag)) }
        $arguments+=$using:Url
        $status=(& curl.exe @arguments)
        if($LASTEXITCODE -ne 0 -or $status -ne '206' -or (Get-Item -LiteralPath ($part+'.partial')).Length -ne $expected) { throw "Range failed: $index ($status)" }
        Move-Item -LiteralPath ($part+'.partial') -Destination $part -Force
        Write-Output "PART_COMPLETE=$index"
    } -ThrottleLimit 3
    $assembled=$Destination+'.assembled'
    $output=[IO.File]::Create($assembled)
    try {
        for($index=0;$index -lt $count;$index++) {
            $sourceStream=[IO.File]::OpenRead((Join-Path $chunkRoot ('part-'+$index.ToString('D4'))))
            try { $sourceStream.CopyTo($output) } finally { $sourceStream.Dispose() }
        }
    } finally { $output.Dispose() }
    if((Get-Item -LiteralPath $assembled).Length -ne $Size) { throw 'Assembled archive length mismatch.' }
    if($Hash -and (Get-FileHash -LiteralPath $assembled -Algorithm SHA256).Hash -ne $Hash) { throw 'Assembled archive SHA256 mismatch.' }
    Move-Item -LiteralPath $assembled -Destination $Destination -Force
}
if($Kind -eq 'Tesseract') {
    Get-CimInstance Win32_Process -Filter "Name='micromamba.exe'" | Where-Object { $_.CommandLine -like ('*'+$environmentRoot+'*') -and $_.CommandLine -like '*runtimes\ocr*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    $metadataFile=Join-Path $environmentRoot 'manifests\tesseract-package.json'
    if(!(Test-Path -LiteralPath $metadataFile)) {
        $metadata=Invoke-RestMethod -Uri 'https://api.anaconda.org/package/conda-forge/tesseract' -Headers @{'User-Agent'='Match-Trajectory-environment-setup'} -TimeoutSec 45
        $entry=$metadata.files | Where-Object basename -eq 'win-64/tesseract-5.5.3-he87eeb8_0.conda' | Select-Object -First 1
        if(!$entry) { throw 'Pinned Tesseract package unavailable.' }
        $entry | Select-Object version,basename,size,sha256 | ConvertTo-Json | Set-Content -LiteralPath $metadataFile -Encoding utf8
    }
    $info=Get-Content -LiteralPath $metadataFile -Raw | ConvertFrom-Json
    $destination=Join-Path $environmentRoot ('downloads\'+[IO.Path]::GetFileName($info.basename))
    Get-Ranged ('https://api.anaconda.org/download/conda-forge/tesseract/'+$info.version+'/'+$info.basename) $destination $info.size $info.sha256
    $cache=Join-Path $environmentRoot ('cache\conda\https\conda.anaconda.org\conda-forge\'+($info.basename -replace '/','\'))
    New-Item -ItemType Directory -Path (Split-Path $cache -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $destination -Destination $cache -Force
    Write-Output 'TESSERACT_ARCHIVE_SHA256_VERIFIED'
    & (Join-Path $PSScriptRoot 'Initialize-Workspace.ps1') -Stage OCR
    if($LASTEXITCODE -ne 0) { throw 'OCR setup did not complete after verified download.' }
} else {
    Get-CimInstance Win32_Process -Filter "Name='curl.exe'" | Where-Object { $_.CommandLine -like ('*'+$environmentRoot+'*') -and $_.CommandLine -like '*Docker-Desktop-Installer.exe.partial*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    $url='https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
    $head=(& curl.exe -4 --head --fail --location --connect-timeout 10 --max-time 30 --silent --show-error $url | Out-String)
    $sizeMatch=[regex]::Match($head,'(?im)^Content-Length:\s*(\d+)')
    $tagMatch=[regex]::Match($head,'(?im)^ETag:\s*([^\r\n]+)')
    if(!$sizeMatch.Success -or !$tagMatch.Success) { throw 'Cannot determine immutable Docker download boundaries.' }
    $installer=Join-Path $environmentRoot 'downloads\Docker-Desktop-Installer.exe'
    Get-Ranged $url $installer ([long]$sizeMatch.Groups[1].Value) '' $tagMatch.Groups[1].Value.Trim()
    $signature=Get-AuthenticodeSignature -LiteralPath $installer
    if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Docker') { throw 'Docker installer signature verification failed.' }
    Save-Paths @{dockerInstaller=$installer;dockerInstallRoot=(Join-Path $environmentRoot 'runtimes\docker-desktop');dockerDataRoot=(Join-Path $environmentRoot 'docker-data')}
    [pscustomobject]@{Installer=$installer;Signature='Valid';Signer=$signature.SignerCertificate.Subject;EngineInstalled=$false;WSL2Ready=$false;Reason='No usable modern WSL2 detected; no Windows system components installed under the D-drive-only constraint.'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $environmentRoot 'manifests\docker-readiness.json') -Encoding utf8
    Write-Output 'DOCKER_INSTALLER_SIGNATURE_VERIFIED_ENGINE_NOT_CONFIGURED'
}
