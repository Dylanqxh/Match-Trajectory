import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_start_app_can_force_a_frontend_rebuild_before_python_starts():
    script = (ROOT / "scripts" / "Start-App.ps1").read_text(encoding="utf-8")
    helper = (ROOT / "scripts" / "FrontendBuild.ps1").read_text(encoding="utf-8")

    assert "[switch]$RebuildFrontend" in script
    assert "web\\dist\\index.html" in script
    assert "Invoke-FrontendBuildIfNeeded" in script
    assert script.index("Invoke-FrontendBuildIfNeeded") < script.index("python @appArguments")
    assert "Frontend build failed" in helper


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not installed; static script check still runs")
def test_existing_dist_stays_until_rebuild_is_requested_and_a_failed_build_stops():
    helper = ROOT / "scripts" / "FrontendBuild.ps1"
    probe = r"""
$ErrorActionPreference = 'Stop'
. '__FRONTEND_BUILD_HELPER__'
if (Test-FrontendRebuildRequired -DistReady $true) { throw 'existing dist was treated as missing' }
if (-not (Test-FrontendRebuildRequired -RebuildFrontend -DistReady $true)) { throw 'explicit rebuild ignored an existing dist' }
if (-not (Test-FrontendRebuildRequired -DistReady $false)) { throw 'missing dist did not require a build' }
$built = $false
Invoke-FrontendBuildIfNeeded -DistReady $true -Build { $script:built = $true; $global:LASTEXITCODE = 0 }
if ($built) { throw 'existing dist was rebuilt without -RebuildFrontend' }
$built = $false
Invoke-FrontendBuildIfNeeded -RebuildFrontend -DistReady $true -Build { $script:built = $true; $global:LASTEXITCODE = 0 }
if (-not $built) { throw '-RebuildFrontend did not rebuild an existing dist' }
$built = $false
Invoke-FrontendBuildIfNeeded -DistReady $false -Build { $script:built = $true; $global:LASTEXITCODE = 0 }
if (-not $built) { throw 'missing dist did not rebuild' }
$continued = $false
try {
    Invoke-FrontendBuildIfNeeded -RebuildFrontend -DistReady $true -Build { $global:LASTEXITCODE = 3 }
    $continued = $true
} catch {
    if ($_.Exception.Message -notmatch 'Frontend build failed') { throw }
}
if ($continued) { throw 'a failed frontend build continued' }
Write-Output 'ok'
""".replace("__FRONTEND_BUILD_HELPER__", helper.as_posix())
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "ok" in result.stdout
