import socket

import pytest


def test_busy_port_falls_back_to_another_reserved_loopback_socket():
    from app.cli import bind_local_socket

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        with bind_local_socket(occupied.getsockname()[1]) as reserved:
            assert reserved.getsockname()[0] == "127.0.0.1"
            assert reserved.getsockname()[1] != occupied.getsockname()[1]


def test_workspace_lock_prevents_two_services_writing_the_same_workspace(tmp_path):
    from app.cli import WorkspaceBusy, workspace_lock

    with workspace_lock(tmp_path), pytest.raises(WorkspaceBusy), workspace_lock(tmp_path):
        pytest.fail("second writer entered")
    with workspace_lock(tmp_path):
        pass


def test_startup_rejects_invalid_port():
    from app.cli import bind_local_socket

    with pytest.raises(ValueError):
        bind_local_socket(70000)


def test_cli_output_is_utf8_even_with_legacy_pipe_encoding():
    import os
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "app.cli", "--help"], capture_output=True, check=False,
                            env=dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="gbk"), timeout=15)
    assert result.returncode == 0
    assert "本地简历工作台" in result.stdout.decode("utf-8")
