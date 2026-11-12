import asyncio
from types import SimpleNamespace

import pytest

from app.generation_service import GenerationService
from app.generation_models import Draft
from app.jobs import JobStore
from app.model_client import Completion, ModelRegistry
from app.models import Item, ResumeContent, Section
from app.providers import ProviderConfig
from app.store import Conflict, ResumeStore
from app.skill import build_evidence, load_skill


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
    def __init__(self, text):
        self.text = text
        self.contexts = []

    async def propose_edit(self, config, context, schema):
        self.contexts.append(context)
        current = ResumeContent.model_validate(context["current_content"])
        current.sections[0].items[0].text = self.text
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


def test_resume_agent_proposes_then_applies_a_new_revision_without_sending_header_fields(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, client = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")

    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    proposed = asyncio.run(service.post(session["id"], AgentMessageInput(text="突出接口性能优化结果")))

    assert proposed["target"]["revision"] == 1
    assert proposed["proposal"]["state"] == "ready"
    assert proposed["proposal"]["changes"] == [{
        "item_id": "query",
        "before": "使用 Java 完成查询接口。",
        "after": "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。",
        "reason": "突出原文中的性能结果",
        "evidence_ids": ["e1"],
    }]
    sent = str(client.contexts)
    assert "林然" not in sent
    assert "linran@example.com" not in sent

    applied = service.apply(session["id"], proposed["proposal"]["id"])

    assert applied["resume"].revision == 2
    assert applied["resume"].content.name == "林然"
    assert applied["resume"].content.contact == "linran@example.com"
    assert applied["resume"].content.sections[0].items[0].text.endswith("300ms。")


def test_resume_agent_blocks_a_new_unsupported_number(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，支撑 100 万用户。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))

    proposed = asyncio.run(service.post(session["id"], AgentMessageInput(text="写得更有影响力")))

    assert proposed["proposal"]["state"] == "blocked"
    assert proposed["proposal"]["issues"]
    with pytest.raises(Conflict, match="风险"):
        service.apply(session["id"], proposed["proposal"]["id"])
    assert store.get(record.id).revision == 1


def test_resume_agent_rejects_a_stale_proposal(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    record = store.create(base_content(), "manual", source_text="使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    proposed = asyncio.run(service.post(session["id"], AgentMessageInput(text="突出性能结果")))
    store.save(record.id, 1, base_content().model_copy(update={"summary": "手工保存的新版本"}))

    with pytest.raises(Conflict, match="变化"):
        service.apply(session["id"], proposed["proposal"]["id"])

    assert store.get(record.id).revision == 2


def test_resume_agent_applies_a_generated_task_candidate_as_a_versioned_resume(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    service, store, _ = agent_service(tmp_path, "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")
    evidence = [row.model_dump() for row in build_evidence("使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。")]
    draft = Draft.model_validate({"sections": [{"id": "project", "title": "项目经历", "kind": "project", "items": [
        {"id": "query", "text": "使用 Java 完成查询接口。", "fact_ids": ["e1"]},
    ]}]})
    inputs = {"request_id": "generated-task-1", "name": "林然", "contact": "linran@example.com",
              "target_role": "后端研发", "source_text": "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。",
              "jd": "", "education": [], "career_stage": "unspecified", "has_career_gap": False,
              "execution_mode": "langgraph", "allow_questions": False, "send_materials": True, "edit_request": "none"}
    skill = load_skill("后端研发", role_direction="backend")
    job = service.jobs.create(inputs, service.registry.current, {}, skill, evidence,
                              extra={"state": "ready", "stage": "done", "draft": draft.model_dump(),
                                     "review": {"verdict": "pass", "issues": []}})

    session = service.create(AgentTargetInput(target_type="job", target_id=job["id"]))
    proposed = asyncio.run(service.post(session["id"], AgentMessageInput(text="补上原文里的性能结果")))
    applied = service.apply(session["id"], proposed["proposal"]["id"])

    assert applied["resume"].revision == 2
    assert applied["session"]["target"]["type"] == "resume"
    assert applied["resume"].content.sections[0].items[0].text.endswith("300ms。")
