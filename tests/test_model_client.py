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


def test_total_model_deadline_closes_stream(monkeypatch):
    from app import model_client

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            await asyncio.sleep(0.2)
            yield b" "

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    monkeypatch.setattr(model_client, "REQUEST_TIMEOUT", 0.02)
    client = model_client.ModelClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream)))
    with pytest.raises(ProviderError, match="超时"):
        asyncio.run(client.complete(config(), "review", {}, Review))
    assert stream.closed


def test_schema_error_has_safe_field_diagnostics_without_remote_values():
    from app.model_client import ModelClient, ModelOutputError

    bad = json.dumps({"verdict": "pass", "issues": "never-print-this-secret", "never-print-this-secret": "private material"})
    with pytest.raises(ModelOutputError) as caught:
        asyncio.run(ModelClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response(bad)))).complete(
            config(), "review", {}, Review))
    diagnostics = caught.value.diagnostic
    assert diagnostics["category"] == "schema"
    assert any(field["path"] == "/issues" and field["type"] == "list_type" for field in diagnostics["fields"])
    assert "never-print-this-secret" not in json.dumps(diagnostics)
    assert "private material" not in json.dumps(diagnostics)


def test_schema_exposes_required_summary_id_and_request_explains_format():
    from app.generation_models import Draft
    from app.model_client import ModelClient

    schema = Draft.model_json_schema()
    assert any(definition.get("properties", {}).get("id", {}).get("const") == "__summary" for definition in schema["$defs"].values())

    def handler(request):
        body = json.loads(request.content)
        context = json.loads(body["messages"][1]["content"])
        assert context["format_examples"][0]["sections"][0]["items"][0]["fact_ids"] == ["e1"]
        assert "__summary" in body["messages"][0]["content"]
        return httpx.Response(200, json=response('{"sections":[{"id":"s1","title":"项目经历","items":[{"id":"i1","text":"原文陈述","fact_ids":["e1"]}]}]}'))

    asyncio.run(ModelClient(transport=httpx.MockTransport(handler)).complete(config(), "draft", {"evidence": [{"id": "e1", "text": "原文陈述"}]}, Draft))


def test_duplicate_ids_are_diagnosed_without_echoing_resume_text():
    from app.generation_models import Draft
    from app.model_client import ModelClient, ModelOutputError

    candidate = {"sections": [{"id": "s1", "title": "项目经历", "items": [
        {"id": "same", "text": "private resume text", "fact_ids": ["e1"]},
        {"id": "same", "text": "another private statement", "fact_ids": ["e1"]},
    ]}]}
    with pytest.raises(ModelOutputError) as caught:
        asyncio.run(ModelClient(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json=response(json.dumps(candidate))))).complete(config(), "draft", {}, Draft))
    assert caught.value.diagnostic["fields"][0]["rule"] == "unique_ids"
    assert "private" not in json.dumps(caught.value.diagnostic)


def test_review_format_examples_do_not_supply_a_canned_quality_verdict():
    from app.model_client import format_examples

    assert format_examples("review", {"evidence": [{"id": "e1"}]}) == []
