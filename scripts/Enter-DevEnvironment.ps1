$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$environmentRoot=Join-Path (Split-Path $projectRoot -Parent) '.dev-environment'
$pathsFile=Join-Path $environmentRoot 'manifests\paths.json'
if(!(Test-Path -LiteralPath $pathsFile)) { throw "Environment is not provisioned: $pathsFile" }
$paths=Get-Content -LiteralPath $pathsFile -Raw | ConvertFrom-Json -AsHashtable
$env:MATCH_TRAJECTORY_ENV_ROOT=$environmentRoot
$env:TEMP=Join-Path $environmentRoot 'tmp'
$env:TMP=$env:TEMP
$env:UV_CACHE_DIR=Join-Path $environmentRoot 'cache\uv'
$env:UV_PYTHON_INSTALL_DIR=Join-Path $environmentRoot 'runtimes\python'
$env:UV_PYTHON_BIN_DIR=Join-Path $environmentRoot 'runtimes\python-bin'
$env:UV_TOOL_DIR=Join-Path $environmentRoot 'runtimes\uv-tools'
$env:UV_TOOL_BIN_DIR=Join-Path $environmentRoot 'runtimes\uv-tools-bin'
$env:UV_PROJECT_ENVIRONMENT=Join-Path $projectRoot '.venv'
$env:UV_PYTHON_INSTALL_REGISTRY='0'
$env:UV_NO_MODIFY_PATH='1'
$env:UV_SYSTEM_CERTS='true'
$env:PIP_CACHE_DIR=Join-Path $environmentRoot 'cache\pip'
$env:NPM_CONFIG_CACHE=Join-Path $environmentRoot 'cache\npm'
$env:NPM_CONFIG_PREFIX=Join-Path $environmentRoot 'runtimes\npm-global'
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $environmentRoot 'runtimes\playwright'
$env:CONDA_PKGS_DIRS=Join-Path $environmentRoot 'cache\conda'
$env:MAMBA_ROOT_PREFIX=Join-Path $environmentRoot 'runtimes\mamba'
$env:MAMBA_REGISTER_ENVS='false'
$env:HF_HOME=Join-Path $environmentRoot 'cache\huggingface'
$env:XDG_CACHE_HOME=Join-Path $environmentRoot 'cache\xdg'
$env:DOCKER_CONFIG=Join-Path $environmentRoot 'docker-config'
$bins=@((Join-Path $projectRoot '.venv\Scripts'),$paths.node,(Split-Path $paths.uv -Parent))
if($paths.tesseract) { $bins+=(Split-Path $paths.tesseract -Parent); $bins+=(Join-Path $paths.ocrRoot 'Library\bin') }
if($paths.soffice) { $bins+=(Split-Path $paths.soffice -Parent) }
if($paths.docker) { $bins+=(Split-Path $paths.docker -Parent) }
if($paths.tessdata) { $env:TESSDATA_PREFIX=$paths.tessdata }
$env:PATH=($bins -join ';')+';'+$env:PATH
Set-Alias -Name npm -Value (Join-Path $paths.node 'npm.cmd') -Scope Global
Set-Location -LiteralPath $projectRoot
Write-Host 'Match-Trajectory development environment loaded (project-local runtimes and caches).'
