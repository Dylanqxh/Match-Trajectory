import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.draft_normalize import normalize_draft_payload
from app.generation_models import Draft
from app.main import create_app
from tests_support import fixture_quality

SOURCE = "使用 Python 完成睡眠分期检测，并整理 SoccerNet 实验数据。在实验室实习。2024.09 至 2026.06。"
BAD_HIGHLIGHT = "这段高亮并不在句子中"


def brittle_draft():
    return {"summary": None, "education": [], "sections": [
        {"id": "skills", "title": "专业技能", "kind": "skills", "items": [
            {"id": "sk1", "text": "使用 Python 完成睡眠分期检测。", "fact_ids": ["e1"]}]},
        {"id": "proj", "title": "项目", "kind": "project", "items": [
            {"id": "p1", "text": "使用 Python 完成睡眠分期检测，并整理 SoccerNet 实验数据。", "fact_ids": ["e1"]}]},
        {"id": "work", "title": "工作／实习经历", "kind": "work", "start_date": "2024.09", "end_date": "2026.06", "items": [
            {"id": "实习-1", "text": "在实验室实习并整理 SoccerNet 实验数据。", "fact_ids": "e1", "highlights": [BAD_HIGHLIGHT]}]},
    ]}


def test_brittle_project_item_is_normalized_without_adding_words():
    raw = brittle_draft()
    with_bad_id = raw["sections"][2]["items"][0]
    with pytest.raises(ValidationError):
        Draft.model_validate(raw)
    normalized = normalize_draft_payload(raw, ["e1"])
    draft = Draft.model_validate(normalized)
    item = draft.sections[2].items[0]
    assert item.text == with_bad_id["text"]
    assert item.highlights == []
    assert item.fact_ids == ["e1"]
    assert draft.sections[2].start_date == "2024-09"
    assert draft.sections[2].end_date == "2026-06"
    assert "精通" not in item.text
    assert "【待补充" not in item.text


def test_model_client_accepts_the_same_item_shape():
    from app.model_client import ModelClient
    from app.providers import ProviderConfig

    def handler(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(brittle_draft(), ensure_ascii=False)}}]})

    client = ModelClient(transport=httpx.MockTransport(handler))
    config = ProviderConfig(provider="custom", base_url="https://model.example/v1", model="test", api_key="not-a-real-key")
    draft = asyncio.run(client.complete(config, "draft", {"instructions": "只根据原文", "evidence": [{"id": "e1", "text": SOURCE}]}, Draft)).value
    assert draft.sections[2].items[0].text == "在实验室实习并整理 SoccerNet 实验数据。"
    assert BAD_HIGHLIGHT not in draft.sections[2].items[0].highlights


def test_algorithm_draft_with_brittle_item_reaches_ready(tmp_path, monkeypatch):
    from app import providers
    from app.model_client import ModelClient

    def handler(request):
        payload = json.loads(request.content)
        system = payload["messages"][0]["content"]
        user = payload["messages"][-1]["content"]
        if "Return only this JSON" in user:
            content = {"ok": True}
        elif "当前阶段：plan" in system:
            content = {"decision": "draft", "selected_fact_ids": ["e1"]}
        elif "当前阶段：review" in system:
            content = {"verdict": "pass", "issues": [], "quality": fixture_quality()}
        else:
            content = brittle_draft()
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content, ensure_ascii=False)}}]})

    real = providers.probe_provider

    async def probe(config):
        return await real(config, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(providers, "probe_provider", probe)
    app = create_app(tmp_path, model_client=ModelClient(transport=httpx.MockTransport(handler)))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.get("/api/session")
        assert client.post("/api/model-settings/test", json={
            "provider": "custom", "base_url": "https://model.example/v1", "model": "test", "api_key": "api-test-secret",
        }).status_code == 200
        created = client.post("/api/generation-jobs", json={
            "request_id": "algo-draft1", "name": "测试", "contact": "job@example.com", "target_role": "算法工程师",
            "source_text": SOURCE, "send_materials": True,
        })
        assert created.status_code == 201, created.text
        job_id = created.json()["id"]
        for _ in range(80):
            row = client.get(f"/api/generation-jobs/{job_id}").json()
            if row["state"] not in ("queued", "running"):
                break
            time.sleep(0.025)
        else:
            raise AssertionError("job did not finish")
        body = json.dumps(row.get("draft"), ensure_ascii=False)
        assert row["state"] == "ready", row.get("error")
        assert "SoccerNet" in body
        assert "睡眠分期" in body
        assert BAD_HIGHLIGHT not in body
        assert "精通" not in body
        assert "【待补充" not in body
        assert "/sections" not in (row.get("error") or "")
