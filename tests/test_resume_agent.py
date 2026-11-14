import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.generation_models import Draft
from app.generation_service import GenerationService
from app.jobs import JobStore
from app.model_client import Completion, ModelRegistry
from app.models import Item, ResumeContent, Section
from app.providers import ProviderConfig
from app.skill import build_evidence, load_skill
from app.store import Conflict, ResumeStore


def base_content():
    return ResumeContent(
        name="林然",
        contact="linran@example.com",
        target_role="后端研发",
        sections=[Section(id="project", title="项目经历", kind="project", items=[
            Item(id="query", text="使用 Java 完成查询接口。"),
        ])],
    )


class ScriptedEditClient:
    def __init__(self, text, before_return=None):
        self.text = text
        self.before_return = before_return
        self.contexts = []

    async def propose_edit(self, config, context, schema):
        self.contexts.append(context)
        current = ResumeContent.model_validate(context["current_content"])
        current.sections[0].items[0].text = self.text
        if self.before_return:
            self.before_return()
        return Completion(schema(
            reply="我整理了一处可核对的修改。",
            content=current,
            reasons=[{"item_id": "query", "reason": "突出原文中的性能结果", "evidence_ids": ["e1"]}],
        ), {})


def agent_service(tmp_path, output_text):
    from app.resume_agent import AgentService

    store = ResumeStore(tmp_path / "resumes.sqlite3")
    jobs = JobStore(store)
    registry = ModelRegistry()
    registry.register(ProviderConfig(
        provider="custom", base_url="https://model.example/v1", model="fixture", api_key="secret",
    ))
    client = ScriptedEditClient(output_text)
    generation = GenerationService(store, jobs, registry, client)
    service = AgentService(SimpleNamespace(
        store=store, jobs=jobs, registry=registry, client=client, adopt=generation.adopt,
    ))
    return service, store, client


def ready_job(service):
    evidence = [row.model_dump() for row in build_evidence("使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")]
    draft = Draft.model_validate({"sections": [{"id": "project", "title": "项目经历", "kind": "project", "items": [
        {"id": "query", "text": "使用 Java 完成查询接口。", "fact_ids": ["e1"]},
    ]}]})
    inputs = {"request_id": "generated-task-1", "name": "林然", "contact": "linran@example.com",
              "target_role": "后端研发", "source_text": "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。",
              "jd": "", "education": [], "career_stage": "unspecified", "has_career_gap": False,
              "execution_mode": "langgraph", "allow_questions": False, "send_materials": True, "edit_request": "none"}
    skill = load_skill("后端研发", role_direction="backend")
    return service.jobs.create(inputs, service.registry.current, {}, skill, evidence,
                               extra={"state": "ready", "stage": "done", "draft": draft.model_dump(),
                                      "review": {"verdict": "pass", "issues": []}})


def test_resume_agent_auto_applies_a_safe_edit_without_sending_header_fields(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, client = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")

    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="突出接口性能优化结果")))

    assert result["resume"].revision == 2
    assert result["session"]["target"]["revision"] == 2
    assert result["session"]["proposal"]["state"] == "applied"
    assert result["session"]["can_undo"] is True
    assert result["session"]["proposal"]["changes"] == [{
        "item_id": "query",
        "before": "使用 Java 完成查询接口。",
        "after": "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。",
        "reason": "突出原文中的性能结果",
        "evidence_ids": ["e1"],
    }]
    sent = str(client.contexts)
    assert "林然" not in sent
    assert "linran@example.com" not in sent
    assert result["resume"].content.name == "林然"
    assert result["resume"].content.contact == "linran@example.com"
    assert result["resume"].content.sections[0].items[0].text.endswith("300ms。")


def test_resume_agent_blocks_an_unsupported_edit_but_accepts_the_next_clarification(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，支撑 100 万用户。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))

    blocked = asyncio.run(service.post(session["id"], AgentMessageInput(text="写得更有影响力")))

    assert blocked["resume"] is None
    assert blocked["session"]["proposal"]["state"] == "blocked"
    assert blocked["session"]["proposal"]["issues"]
    assert store.get(record.id).revision == 1

    service.client.text = "完成 Java 查询接口开发。"
    fixed = asyncio.run(service.post(session["id"], AgentMessageInput(text="不要加数字，只精简措辞")))

    assert fixed["resume"].revision == 2
    assert fixed["session"]["proposal"]["state"] == "applied"
    assert fixed["resume"].content.sections[0].items[0].text == "完成 Java 查询接口开发。"


def test_resume_agent_does_not_create_a_revision_for_a_noop_response(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))

    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="保持事实不变，看看是否需要调整")))

    assert result["resume"] is None
    assert result["session"]["proposal"]["state"] == "unchanged"
    assert result["session"]["can_undo"] is False
    assert store.get(record.id).revision == 1


def test_resume_agent_rejects_a_stale_auto_apply_without_overwriting_manual_work(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, client = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    client.before_return = lambda: store.save(
        record.id, 1, base_content().model_copy(update={"summary": "手工保存的新版本"}),
    )

    with pytest.raises(Conflict, match="变化"):
        asyncio.run(service.post(session["id"], AgentMessageInput(text="突出性能结果")))

    assert store.get(record.id).revision == 2
    assert store.get(record.id).content.summary == "手工保存的新版本"


def test_resume_agent_auto_applies_a_generated_task_candidate_as_a_versioned_resume(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, _store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    job = ready_job(service)

    session = service.create(AgentTargetInput(target_type="job", target_id=job["id"]))
    applied = asyncio.run(service.post(session["id"], AgentMessageInput(text="补上原文里的性能结果")))

    assert applied["resume"].revision == 2
    assert applied["session"]["target"]["type"] == "resume"
    assert applied["resume"].content.sections[0].items[0].text.endswith("300ms。")


def test_job_apply_conflict_does_not_create_an_orphan_agent_job(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    job = ready_job(service)
    session = service.create(AgentTargetInput(target_type="job", target_id=job["id"]))
    def race():
        adopted = service.workflow.adopt(job["id"])
        store.save(adopted.id, adopted.revision, adopted.content.model_copy(update={"summary": "用户刚保存的新版本"}))

    service.client.before_return = race
    job_count = len(service.jobs.list())

    with pytest.raises(Conflict, match="已经被采用并修改"):
        asyncio.run(service.post(session["id"], AgentMessageInput(text="补上原文里的性能结果")))

    assert len(service.jobs.list()) == job_count


def test_resume_agent_undo_restores_the_base_as_a_new_revision(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    applied = asyncio.run(service.post(session["id"], AgentMessageInput(text="突出性能结果")))

    undone = service.undo(session["id"])

    assert applied["resume"].revision == 2
    assert undone["resume"].revision == 3
    assert undone["resume"].content == base_content()
    assert undone["session"]["can_undo"] is False
    assert [row.revision for row in store.history(record.id)] == [1, 2, 3]


def test_resume_agent_rejects_stale_undo_without_overwriting_manual_work(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    applied = asyncio.run(service.post(session["id"], AgentMessageInput(text="突出性能结果")))
    manual = store.save(record.id, applied["resume"].revision, applied["resume"].content.model_copy(update={"summary": "手工补充"}))

    with pytest.raises(Conflict, match="变化"):
        service.undo(session["id"])

    assert store.get(record.id).revision == manual.revision
    assert store.get(record.id).content.summary == "手工补充"


def api_transport(request):
    payload = json.loads(request.content)
    user = payload["messages"][-1]["content"]
    if "Return only this JSON" in user:
        content = {"ok": True}
    else:
        data = json.loads(user)
        candidate = data["current_content"]
        candidate["sections"][0]["items"][0]["text"] = "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。"
        content = {"reply": "已生成一处修改提案。", "content": candidate,
                   "reasons": [{"item_id": "query", "reason": "补充原文中的性能结果", "evidence_ids": ["e1"]}]}
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content, ensure_ascii=False)}}]})


def open_agent_client(tmp_path, monkeypatch):
    from app import providers
    from app.main import create_app
    from app.model_client import ModelClient

    real_probe = providers.probe_provider

    async def probe(config):
        return await real_probe(config, transport=httpx.MockTransport(api_transport))

    monkeypatch.setattr(providers, "probe_provider", probe)
    app = create_app(tmp_path, model_client=ModelClient(transport=httpx.MockTransport(api_transport)))
    client = TestClient(app, base_url="http://127.0.0.1")
    client.__enter__()
    client.get("/api/session")
    settings = {"provider": "custom", "base_url": "https://model.example/v1", "model": "fixture", "api_key": "secret"}
    assert client.post("/api/model-settings/test", json=settings).status_code == 200
    return client, app


def test_agent_api_reuses_a_target_session(tmp_path, monkeypatch):
    client, app = open_agent_client(tmp_path, monkeypatch)
    try:
        record = app.state.store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
        first = client.post("/api/agent/sessions", json={"target_type": "resume", "target_id": record.id})
        second = client.post("/api/agent/sessions", json={"target_type": "resume", "target_id": record.id})

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
    finally:
        client.__exit__(None, None, None)


def test_agent_api_rejects_a_task_without_a_candidate(tmp_path, monkeypatch):
    client, _ = open_agent_client(tmp_path, monkeypatch)
    try:
        job = client.post("/api/generation-jobs", json={"request_id": "empty-agent-task", "target_role": "后端研发"}).json()

        response = client.post("/api/agent/sessions", json={"target_type": "job", "target_id": job["id"]})

        assert response.status_code == 409
        assert "候选" in response.text
    finally:
        client.__exit__(None, None, None)


def test_agent_api_auto_applies_and_can_undo(tmp_path, monkeypatch):
    client, app = open_agent_client(tmp_path, monkeypatch)
    try:
        record = app.state.store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
        session = client.post("/api/agent/sessions", json={"target_type": "resume", "target_id": record.id}).json()
        applied = client.post(f"/api/agent/sessions/{session['id']}/messages", json={"text": "补上性能结果"})
        assert applied.status_code == 200, applied.text
        assert applied.json()["resume"]["revision"] == 2

        undone = client.post(f"/api/agent/sessions/{session['id']}/undo")

        assert undone.status_code == 200, undone.text
        assert undone.json()["resume"]["revision"] == 3
        assert undone.json()["resume"]["content"]["sections"][0]["items"][0]["text"] == "使用 Java 完成查询接口。"
    finally:
        client.__exit__(None, None, None)
