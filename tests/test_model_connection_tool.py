import json

import httpx
import pytest


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
