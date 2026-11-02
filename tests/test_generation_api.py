import json
import time

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from tests_support import fixture_quality


def transport(request):
    payload = json.loads(request.content)
    if "Return only this JSON" in payload["messages"][-1]["content"]:
        content = {"ok": True}
    else:
        system = payload["messages"][0]["content"]
        if "当前阶段：plan" in system:
            content = {"decision": "draft", "selected_fact_ids": ["e1"]}
        elif "当前阶段：review" in system:
            content = {"verdict": "pass", "issues": [], "quality": fixture_quality()}
        else:
            content = {"sections": [{"id": "projects", "title": "项目经历", "items": [
                {"id": "item1", "text": "使用 Java 完成查询接口。", "fact_ids": ["e1"]},
            ]}]}
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content, ensure_ascii=False)}}]})


def wait_for_job(client, job_id):
    for _ in range(80):
        row = client.get(f"/api/generation-jobs/{job_id}").json()
        if row["state"] not in ("queued", "running"):
            return row
        time.sleep(0.025)
    raise AssertionError("job did not finish")


def test_api_requires_session_and_material_sending_consent(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/generation-jobs").status_code == 401
        client.get("/api/session")
        response = client.post("/api/generation-jobs", json={"request_id": "request-001", "target_role": "Java", "source_text": "做了项目"})
        assert response.status_code == 422
        assert "确认" in response.text


def test_api_model_settings_generation_adoption_and_export(tmp_path, monkeypatch):
    from app import providers
    from app.model_client import ModelClient

    real_probe = providers.probe_provider

    async def probe(config):
        return await real_probe(config, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(providers, "probe_provider", probe)
    app = create_app(tmp_path, model_client=ModelClient(transport=httpx.MockTransport(transport)))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.get("/api/session")
        settings = {"provider": "custom", "base_url": "https://model.example/v1", "model": "test", "api_key": "api-test-secret"}
        response = client.post("/api/model-settings/test", json=settings)
        assert response.status_code == 200 and response.json()["config_revision"]
        payload = {"request_id": "request-001", "target_role": "Java", "source_text": "使用 Java 完成查询接口。",
                   "name": "测试用户", "contact": "test@example.com", "send_materials": True}
        created = client.post("/api/generation-jobs", json=payload)
        assert created.status_code == 201
        job = wait_for_job(client, created.json()["id"])
        assert job["state"] == "ready", job
        assert "api-test-secret" not in json.dumps(job)
        resume = client.post(f"/api/generation-jobs/{job['id']}/adopt").json()
        assert resume["ai"]["review_status"] == "passed"
        client.post(f"/api/resumes/{resume['id']}/confirm", json={"expected_revision": 1})
        exported = client.post(f"/api/resumes/{resume['id']}/exports", json={"expected_revision": 1, "format": "docx"})
        assert exported.status_code == 200


def test_framework_is_available_without_credentials_and_bad_answer_is_rejected(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        client.get("/api/session")
        created = client.post("/api/generation-jobs", json={"request_id": "empty-0001", "target_role": "算法"})
        assert created.status_code == 201
        assert created.json()["framework"] is True
        invalid = client.post(f"/api/generation-jobs/{created.json()['id']}/answer", json={"question_group": "old", "skip": True})
        assert invalid.status_code == 409
