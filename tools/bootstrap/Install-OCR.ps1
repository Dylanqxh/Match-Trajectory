. (Join-Path $PSScriptRoot 'Common.ps1')
$cachedTesseract=Join-Path $environmentRoot 'cache\conda\https\conda.anaconda.org\conda-forge\win-64\tesseract-5.5.3-he87eeb8_0.conda'
if(!(Test-Path -LiteralPath $cachedTesseract) -or (Get-Item -LiteralPath $cachedTesseract).Length -ne 178967988) {
    & (Join-Path $PSScriptRoot 'Install-Ranged.ps1') -Kind Tesseract
    if($LASTEXITCODE -ne 0) { throw 'Tesseract verified archive preparation failed.' }
    exit 0
}
$release=Invoke-RestMethod -Uri 'https://api.github.com/repos/mamba-org/micromamba-releases/releases/latest' -Headers @{'User-Agent'='Match-Trajectory-environment-setup'} -TimeoutSec 45
$asset=$release.assets | Where-Object { $_.name -eq 'micromamba-win-64' -or $_.name -eq 'micromamba-win-64.exe' } | Select-Object -First 1
if(!$asset) { throw 'Windows micromamba executable not found in official release.' }
$mamba=Join-Path $environmentRoot 'runtimes\micromamba\micromamba.exe'
$digest=if($asset.digest -match '^sha256:(.*)$') { $Matches[1] } else { '' }
Get-Download $asset.browser_download_url $mamba $digest
$ocr=Join-Path $environmentRoot 'runtimes\ocr'
$mambaRoot=Join-Path $environmentRoot 'runtimes\mamba'
& $mamba create --no-rc --yes --root-prefix $mambaRoot --prefix $ocr --override-channels --channel conda-forge 'tesseract=5.5.3'
if($LASTEXITCODE -ne 0) { throw 'Tesseract portable conda environment installation failed.' }
$exe=(Get-ChildItem -LiteralPath $ocr -Filter tesseract.exe -Recurse | Select-Object -First 1).FullName
if(!$exe) { throw 'Tesseract executable not found.' }
$tessdata=Join-Path $environmentRoot 'runtimes\tessdata'
New-Item -ItemType Directory -Path $tessdata -Force | Out-Null
foreach($lang in @('eng','chi_sim')) {
    Get-Download "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/$lang.traineddata" (Join-Path $tessdata "$lang.traineddata")
}
$env:TESSDATA_PREFIX=$tessdata
$env:PATH=(Split-Path $exe -Parent)+';'+(Join-Path $ocr 'Library\bin')+';'+$env:PATH
& $exe --version
& $exe --list-langs
if($LASTEXITCODE -ne 0) { throw 'Tesseract language validation failed.' }
$fontRoot=Join-Path $environmentRoot 'runtimes\fonts'
Get-Download 'https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf' (Join-Path $fontRoot 'NotoSansCJKsc-Regular.otf')
Get-Download 'https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE' (Join-Path $fontRoot 'LICENSE-NotoSansCJK.txt')
Save-Paths @{tesseract=$exe;tessdata=$tessdata;ocrRoot=$ocr;fonts=$fontRoot}
Write-Output 'OCR_STAGE_COMPLETE'
