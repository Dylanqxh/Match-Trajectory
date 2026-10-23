param([ValidateSet('Runtime','OCR','Office','Docker','DockerCLI','Verify','RangedDocker','RangedTesseract')][string]$Stage='Runtime')
$ErrorActionPreference='Stop'
$environmentRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if([IO.Path]::GetPathRoot($environmentRoot) -eq 'C:\') { throw 'Use a non-C drive workspace for portable runtimes.' }
foreach($part in @('downloads','cache','tmp','logs','runtimes','manifests')) {
    New-Item -ItemType Directory -Path (Join-Path $environmentRoot $part) -Force | Out-Null
}
$env:TEMP=Join-Path $environmentRoot 'tmp'
$env:TMP=$env:TEMP
$env:UV_CACHE_DIR=Join-Path $environmentRoot 'cache\uv'
$env:UV_PYTHON_INSTALL_DIR=Join-Path $environmentRoot 'runtimes\python'
$env:UV_PYTHON_BIN_DIR=Join-Path $environmentRoot 'runtimes\python-bin'
$env:UV_TOOL_DIR=Join-Path $environmentRoot 'runtimes\uv-tools'
$env:UV_TOOL_BIN_DIR=Join-Path $environmentRoot 'runtimes\uv-tools-bin'
$env:UV_PYTHON_INSTALL_BIN='0'
$env:UV_PYTHON_INSTALL_REGISTRY='0'
$env:UV_NO_MODIFY_PATH='1'
$env:UV_SYSTEM_CERTS='true'
$env:NPM_CONFIG_CACHE=Join-Path $environmentRoot 'cache\npm'
$env:NPM_CONFIG_PREFIX=Join-Path $environmentRoot 'runtimes\npm-global'
$env:PIP_CACHE_DIR=Join-Path $environmentRoot 'cache\pip'
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $environmentRoot 'runtimes\playwright'
$env:MAMBA_ROOT_PREFIX=Join-Path $environmentRoot 'runtimes\mamba'
$env:MAMBA_REGISTER_ENVS='false'
$env:CONDA_PKGS_DIRS=Join-Path $environmentRoot 'cache\conda'
$env:HF_HOME=Join-Path $environmentRoot 'cache\huggingface'
$env:XDG_CACHE_HOME=Join-Path $environmentRoot 'cache\xdg'
$env:DOCKER_CONFIG=Join-Path $environmentRoot 'docker-config'
if($Stage.StartsWith('Ranged')) {
    & (Join-Path $PSScriptRoot 'Install-Ranged.ps1') -Kind $Stage.Substring(6)
} else {
    & (Join-Path $PSScriptRoot ('Install-'+$Stage+'.ps1'))
}
exit $LASTEXITCODE
