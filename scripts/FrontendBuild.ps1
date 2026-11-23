function Test-FrontendRebuildRequired {
    param(
        [switch]$RebuildFrontend,
        [bool]$DistReady
    )
    return [bool]($RebuildFrontend -or -not $DistReady)
}

function Invoke-FrontendBuildIfNeeded {
    param(
        [switch]$RebuildFrontend,
        [bool]$DistReady,
        [Parameter(Mandatory)][scriptblock]$Build
    )
    if (-not (Test-FrontendRebuildRequired -RebuildFrontend:$RebuildFrontend -DistReady $DistReady)) { return }
    & $Build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
}
