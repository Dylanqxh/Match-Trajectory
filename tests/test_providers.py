import asyncio
import json

import httpx
import pytest


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
