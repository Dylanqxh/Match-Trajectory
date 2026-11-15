import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent


def success_transport(request):
    assert request.url == "https://relay.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer diagnostic-secret"
    return httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"ok": True})}}],
    })


def test_diagnostic_probe_uses_runtime_protocol_without_returning_the_key():
    from tools.test_model_connection import run_probe

    result = run_probe("https://relay.example/v1", "relay-model", "diagnostic-secret",
                       transport=httpx.MockTransport(success_transport))

    assert result["ok"] is True
    assert result["endpoint"] == "https://relay.example/v1/chat/completions"
    assert result["model"] == "relay-model"
    assert "diagnostic-secret" not in json.dumps(result)


def test_diagnostic_probe_returns_the_safe_runtime_error_category():
    from tools.test_model_connection import run_probe

    transport = httpx.MockTransport(lambda request: httpx.Response(
        401, json={"error": {"message": "bad diagnostic-secret"}},
    ))

    with pytest.raises(RuntimeError) as caught:
        run_probe("https://relay.example/v1", "relay-model", "diagnostic-secret", transport=transport)

    assert caught.value.category == "invalid_key"
    assert "diagnostic-secret" not in str(caught.value)


def test_diagnostic_probe_can_select_the_responses_protocol():
    from tools.test_model_connection import run_probe

    def handler(request):
        assert request.url == "https://relay.example/v1/responses"
        body = json.loads(request.content)
        assert body["store"] is False and "input" in body
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}],
        })

    result = run_probe("https://relay.example/v1", "relay-model", "diagnostic-secret", protocol="responses",
                       transport=httpx.MockTransport(handler))
    assert result["endpoint"] == "https://relay.example/v1/responses"
    assert result["protocol"] == "responses"
    assert "diagnostic-secret" not in json.dumps(result)


def test_documented_direct_script_entrypoint_can_import_the_application():
    result = subprocess.run(
        [sys.executable, "tools/test_model_connection.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert "Chat Completions" in result.stdout
    assert "Responses" in result.stdout
    assert "--protocol" in result.stdout
