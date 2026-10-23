. (Join-Path $PSScriptRoot 'Common.ps1')
$headers=@{'User-Agent'='Match-Trajectory-environment-setup'}
$release=Invoke-RestMethod -Uri 'https://api.github.com/repos/ip7z/7zip/releases/latest' -Headers $headers -TimeoutSec 45
$small=$release.assets | Where-Object name -eq '7zr.exe' | Select-Object -First 1
$full=$release.assets | Where-Object name -match '^7z\d+-x64\.exe$' | Select-Object -First 1
if(!$small -or !$full) { throw 'Official 7-Zip assets unavailable.' }
$sevenRoot=Join-Path $environmentRoot 'runtimes\7zip'
$smallExe=Join-Path $sevenRoot '7zr.exe'
$fullExe=Join-Path $environmentRoot ('downloads\'+$full.name)
Get-Download $small.browser_download_url $smallExe
Get-Download $full.browser_download_url $fullExe
& $smallExe x $fullExe "-o$sevenRoot" -y | Out-File -LiteralPath (Join-Path $environmentRoot 'logs\7zip-extract.log') -Encoding utf8
if($LASTEXITCODE -ne 0) { throw 'Portable 7-Zip extraction failed.' }
$seven=Join-Path $sevenRoot '7z.exe'
if(!(Test-Path -LiteralPath $seven)) { throw 'Full portable 7-Zip unavailable.' }
$catalogUrl='https://download.documentfoundation.org/libreoffice/portable/'
$catalog=(Invoke-WebRequest -Uri $catalogUrl -TimeoutSec 60).Content
$versions=[regex]::Matches($catalog,'href="(\d+\.\d+(?:\.\d+){0,2})/"') | ForEach-Object { $_.Groups[1].Value } | Sort-Object {[version]$_} -Descending
if(!$versions) { throw 'LibreOffice publisher portable release catalog unavailable.' }
$officeUrl=$null
foreach($version in ($versions | Select-Object -First 5)) {
    $releasePage=(Invoke-WebRequest -Uri ($catalogUrl+$version+'/') -TimeoutSec 60).Content
    $found=[regex]::Match($releasePage,'href="([^"/]*LibreOfficePortable_[^"/]*_MultilingualStandard\.paf\.exe)"')
    if($found.Success) { $officeUrl=$catalogUrl+$version+'/'+$found.Groups[1].Value; break }
}
if(!$officeUrl) { throw 'Portable LibreOffice standard archive not found in publisher catalog.' }
$archive=Join-Path $environmentRoot ('downloads\'+([uri]$officeUrl).Segments[-1])
Get-Download $officeUrl $archive
$office=Join-Path $environmentRoot 'runtimes\libreoffice'
New-Item -ItemType Directory -Path $office -Force | Out-Null
& $seven x $archive "-o$office" -y | Out-File -LiteralPath (Join-Path $environmentRoot 'logs\libreoffice-extract.log') -Encoding utf8
if($LASTEXITCODE -ne 0) { throw 'Portable LibreOffice extraction failed.' }
$soffice=(Get-ChildItem -LiteralPath $office -Filter soffice.com -Recurse | Select-Object -First 1).FullName
if(!$soffice) { $soffice=(Get-ChildItem -LiteralPath $office -Filter soffice.exe -Recurse | Select-Object -First 1).FullName }
if(!$soffice) { throw 'LibreOffice executable missing after portable extraction.' }
$officeUserProfile=Join-Path $environmentRoot 'office-profile'
& $soffice ('-env:UserInstallation='+([uri]$officeUserProfile).AbsoluteUri) --headless --version
if($LASTEXITCODE -ne 0) { throw 'LibreOffice startup failed.' }
Save-Paths @{soffice=$soffice;officeProfile=$officeUserProfile;officeSource=$officeUrl}
Write-Output 'OFFICE_STAGE_COMPLETE'
