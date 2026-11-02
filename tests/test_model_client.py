import asyncio
import json

import httpx
import pytest

from app.generation_models import Review
from app.providers import ProviderConfig, ProviderError


def config():
    return ProviderConfig(provider="deepseek", model="deepseek-flash", api_key="never-print-this-secret")


def response(content='{"verdict":"pass","issues":[]}', reason="stop"):
    return {"choices": [{"finish_reason": reason, "message": {"content": content}}], "usage": {"total_tokens": 23}}


def test_deepseek_structured_request_and_usage():
    from app.model_client import ModelClient

    def handler(request):
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        assert len(body["messages"]) == 2
        assert "json" in body["messages"][0]["content"].lower()
        assert "draft_self_evaluation" not in body["messages"][1]["content"]
        return httpx.Response(200, json=response())

    client = ModelClient(transport=httpx.MockTransport(handler))
    completion = asyncio.run(client.complete(config(), "review", {"instructions": "只核对原文", "candidate": {}}, Review))
    assert completion.value.verdict == "pass"
    assert completion.usage["total_tokens"] == 23


@pytest.mark.parametrize(("content", "reason"), [("  ", "stop"), ('{"verdict":', "length"),
                                                      ('{"verdict":"pass","secret":"never-print-this-secret"}', "stop")])
def test_invalid_or_truncated_json_has_safe_error_and_no_hidden_retry(content, reason):
    from app.model_client import ModelClient, ModelOutputError

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response(content, reason))

    with pytest.raises(ModelOutputError) as caught:
        asyncio.run(ModelClient(transport=httpx.MockTransport(handler)).complete(config(), "review", {}, Review))
    assert "never-print-this-secret" not in str(caught.value)
    assert len(calls) == 1


def test_http_error_does_not_echo_remote_secret_or_follow_redirect():
    from app.model_client import ModelClient

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://elsewhere.example"}, text="never-print-this-secret")

    with pytest.raises(ProviderError) as caught:
        asyncio.run(ModelClient(transport=httpx.MockTransport(handler)).complete(config(), "review", {}, Review))
    assert len(calls) == 1
    assert "never-print-this-secret" not in str(caught.value)


def test_large_output_stream_is_closed_before_all_bytes_are_read():
    from app.model_client import ModelClient

    class Stream(httpx.AsyncByteStream):
        reads = 0
        closed = False

        async def __aiter__(self):
            for _ in range(50):
                self.reads += 1
                yield b"x" * 65536

        async def aclose(self):
            self.closed = True

    stream = Stream()
    with pytest.raises(ProviderError):
        asyncio.run(ModelClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream))).complete(
            config(), "review", {}, Review))
    assert stream.reads <= 5 and stream.closed
