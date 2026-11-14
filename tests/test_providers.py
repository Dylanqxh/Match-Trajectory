import asyncio
import json

import httpx
import pytest


def test_popular_provider_presets_have_fixed_official_base_urls():
    from app.providers import PRESETS, ProviderConfig

    assert PRESETS["openai"]["base_url"] == "https://api.openai.com/v1"
    assert PRESETS["anthropic"]["base_url"] == "https://api.anthropic.com/v1"
    assert ProviderConfig(provider="openai", model="gpt-6.1-sol", api_key="test").base_url == "https://api.openai.com/v1"
    assert ProviderConfig(provider="anthropic", model="claude-sonnet-5", api_key="test").base_url == "https://api.anthropic.com/v1"


def test_probe_uses_only_synthetic_text_and_returns_no_secret():
    from app.providers import ProviderConfig, probe_provider

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer unit-test-secret"
        body = json.loads(request.content)
        assert "ok" in body["messages"][0]["content"]
        assert body["model"] == "test-model"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})

    config = ProviderConfig(provider="custom", base_url="https://provider.example/v1", model="test-model", api_key="unit-test-secret")
    result = asyncio.run(probe_provider(config, transport=httpx.MockTransport(handler)))
    assert result["json_probe_passed"] is True
    assert "unit-test-secret" not in json.dumps(result)


def test_anthropic_probe_uses_native_messages_protocol():
    from app.providers import ProviderConfig, probe_provider

    def handler(request):
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "unit-test-secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["model"] == "claude-sonnet-5"
        assert body["messages"] == [{"role": "user", "content": 'Return only this JSON object: {"ok":true}'}]
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": '{"ok":true}'}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 8, "output_tokens": 4},
        })

    config = ProviderConfig(provider="anthropic", model="claude-sonnet-5", api_key="unit-test-secret")
    result = asyncio.run(probe_provider(config, transport=httpx.MockTransport(handler)))

    assert result["json_probe_passed"] is True
    assert result["provider"] == "anthropic"
    assert "unit-test-secret" not in json.dumps(result)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_provider_errors_and_redirects_do_not_echo_secret(status):
    from app.providers import ProviderConfig, ProviderError, probe_provider

    def handler(request):
        return httpx.Response(status, json={"error": "unit-test-secret"}, headers={"location": "https://other.example"})

    config = ProviderConfig(provider="custom", base_url="https://provider.example/v1", model="test-model", api_key="unit-test-secret")
    with pytest.raises(ProviderError) as caught:
        asyncio.run(probe_provider(config, transport=httpx.MockTransport(handler)))
    assert "unit-test-secret" not in str(caught.value)


def test_timeout_and_invalid_json_are_not_success():
    from app.providers import ProviderConfig, ProviderError, probe_provider

    config = ProviderConfig(provider="custom", base_url="https://provider.example", model="x", api_key="test")
    def timeout(request):
        raise httpx.ReadTimeout("test")
    with pytest.raises(ProviderError):
        asyncio.run(probe_provider(config, transport=httpx.MockTransport(timeout)))
    invalid = httpx.MockTransport(lambda request: httpx.Response(
        200, json={"choices": [{"message": {"content": "ok"}}]}))
    with pytest.raises(ProviderError):
        asyncio.run(probe_provider(config, transport=invalid))


def test_remote_cleartext_and_url_credentials_are_rejected():
    from app.providers import ProviderConfig

    for url in ["http://provider.example", "https://user:pass@provider.example", "https://provider.example?key=test"]:
        with pytest.raises(ValueError):
            ProviderConfig(provider="custom", base_url=url, model="x", api_key="test")


def test_failed_probe_preserves_previous_session_settings(tmp_path, monkeypatch):
    from app import providers
    from tests_support import new_client

    real_probe = providers.probe_provider
    async def controlled_probe(config):
        status = 200 if config.model == "working" else 401
        return await real_probe(config, transport=httpx.MockTransport(lambda r: httpx.Response(
            status, json={"choices": [{"message": {"content": '{"ok":true}'}}]})))
    monkeypatch.setattr(providers, "probe_provider", controlled_probe)
    with new_client(tmp_path) as client:
        settings = {"provider": "custom", "base_url": "https://provider.example/v1", "model": "working", "api_key": "keep-this-secret"}
        result = client.post("/api/model-settings/test", json=settings)
        assert result.status_code == 200
        assert "keep-this-secret" not in result.text
        settings["model"] = "broken"
        assert client.post("/api/model-settings/test", json=settings).status_code == 422
        assert client.get("/api/model-settings").json()["model"] == "working"


@pytest.mark.parametrize("key", ["a", "abcd"])
def test_short_keys_are_fully_masked(key):
    from app.providers import ProviderConfig, probe_provider

    config = ProviderConfig(provider="custom", base_url="http://127.0.0.1:12345/v1", model="local", api_key=key)
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, json={"choices": [{"message": {"content": '{"ok":true}'}}]}))
    result = asyncio.run(probe_provider(config, transport=transport))
    assert result["key_mask"] == "••••"


def test_oversized_response_stops_reading_and_closes_stream():
    from app.providers import ProviderConfig, ProviderError, probe_provider

    class LargeStream(httpx.AsyncByteStream):
        reads = 0
        closed = False

        async def __aiter__(self):
            for _ in range(10):
                self.reads += 1
                yield b"x" * 65536

        async def aclose(self):
            self.closed = True

    stream = LargeStream()
    config = ProviderConfig(provider="custom", base_url="https://provider.example", model="test", api_key="test")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(ProviderError):
        asyncio.run(probe_provider(config, transport=transport))
    assert stream.reads <= 3
    assert stream.closed


def test_total_probe_deadline_closes_slow_stream(monkeypatch):
    from app import providers

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.1)
                yield b" "

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    monkeypatch.setattr(providers, "PROBE_TOTAL_TIMEOUT_SECONDS", 0.02, raising=False)
    config = providers.ProviderConfig(provider="custom", base_url="https://provider.example", model="test", api_key="test")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))

    async def run():
        with pytest.raises(providers.ProviderError, match="超时"):
            await asyncio.wait_for(providers.probe_provider(config, transport=transport), timeout=0.5)

    asyncio.run(run())
    assert stream.closed


@pytest.mark.parametrize(("status", "body", "category"), [
    (401, {"error": "invalid api key unit-test-secret"}, "invalid_key"),
    (402, {"error": "insufficient balance unit-test-secret"}, "insufficient_balance"),
    (429, {"error": "rate limit exceeded unit-test-secret"}, "rate_limited"),
    (429, {"error": "insufficient_quota unit-test-secret"}, "insufficient_balance"),
])
def test_probe_classifies_provider_failures_without_echoing_the_key_or_body(status, body, category):
    from app.providers import ProviderConfig, ProviderError, probe_provider

    def handler(request):
        return httpx.Response(status, json=body)

    config = ProviderConfig(provider="custom", base_url="https://provider.example/v1", model="test-model", api_key="unit-test-secret")
    with pytest.raises(ProviderError) as caught:
        asyncio.run(probe_provider(config, transport=httpx.MockTransport(handler)))
    assert caught.value.category == category
    assert "unit-test-secret" not in str(caught.value)
    assert "Traceback" not in str(caught.value)


def test_network_and_timeout_categories_are_distinct():
    from app.providers import ProviderConfig, ProviderError, probe_provider

    config = ProviderConfig(provider="custom", base_url="https://provider.example/v1", model="x", api_key="unit-test-secret")

    def offline(request):
        raise httpx.ConnectError("unit-test-secret")

    with pytest.raises(ProviderError) as offline_error:
        asyncio.run(probe_provider(config, transport=httpx.MockTransport(offline)))
    assert offline_error.value.category == "network"
    assert "unit-test-secret" not in str(offline_error.value)

    def timeout(request):
        raise httpx.ReadTimeout("unit-test-secret")

    with pytest.raises(ProviderError) as timeout_error:
        asyncio.run(probe_provider(config, transport=httpx.MockTransport(timeout)))
    assert timeout_error.value.category == "timeout"
    assert "unit-test-secret" not in str(timeout_error.value)


def test_remembered_key_stays_in_the_keyring_and_out_of_files(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from tests_support import new_client

    saved = {}

    def set_password(service, account, password):
        saved[(service, account)] = password

    def get_password(service, account):
        return saved.get((service, account))

    def delete_password(service, account):
        saved.pop((service, account), None)

    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(
        set_password=set_password, get_password=get_password, delete_password=delete_password))
    from app import providers

    real_probe = providers.probe_provider

    async def probe(config):
        return await real_probe(config, transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})))

    monkeypatch.setattr(providers, "probe_provider", probe)
    with new_client(tmp_path) as client:
        secret = "remember-this-secret"
        response = client.post("/api/model-settings/test", json={
            "provider": "custom", "base_url": "https://provider.example/v1", "model": "test",
            "api_key": secret, "remember": True})
        assert response.status_code == 200, response.text
        assert response.json()["key_storage"] == "keyring"
        assert secret not in response.text
        meta = (tmp_path / "model-remember.json").read_text(encoding="utf-8")
        assert secret not in meta
        assert saved[("match-trajectory", "model-api-key")] == secret
        assert client.get("/api/model-settings").json()["key_storage"] == "keyring"
        assert secret not in client.get("/api/model-settings").text
        assert client.post("/api/model-settings/forget").json()["cleared"] is True
        assert ("match-trajectory", "model-api-key") not in saved


def test_missing_keyring_keeps_the_key_in_memory_only(tmp_path, monkeypatch):
    import sys

    from app import providers
    from tests_support import new_client

    monkeypatch.setitem(sys.modules, "keyring", None)
    real_probe = providers.probe_provider

    async def probe(config):
        return await real_probe(config, transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})))

    monkeypatch.setattr(providers, "probe_provider", probe)
    with new_client(tmp_path) as client:
        secret = "memory-only-secret"
        response = client.post("/api/model-settings/test", json={
            "provider": "custom", "base_url": "https://provider.example/v1", "model": "test",
            "api_key": secret, "remember": True})
        assert response.status_code == 200, response.text
        assert response.json()["key_storage"] == "memory"
        assert "钥匙串" in response.json()["message"]
        assert secret not in response.text
        assert not (tmp_path / "model-remember.json").exists()
