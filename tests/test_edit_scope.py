import asyncio
from types import SimpleNamespace

from app.generation_service import GenerationService
from app.jobs import JobStore
from app.model_client import Completion, ModelRegistry
from app.models import Item, ResumeContent, Section
from app.providers import ProviderConfig
from app.store import ResumeStore

SOURCE = "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。编写测试记录，未上线。"


def content():
    return ResumeContent(
        name="林然", contact="linran@example.com", target_role="后端研发",
        sections=[Section(id="project", title="项目经历", kind="project", items=[
            Item(id="query", text="使用 Java 完成查询接口，响应时间 500ms。", highlights=["500ms"]),
            Item(id="tests", text="编写测试记录。", highlights=["测试记录"]),
        ])],
    )


class ScopeClient:
    def __init__(self, mutate):
        self.mutate = mutate

    async def propose_edit(self, config, context, schema):
        current = ResumeContent.model_validate(context["current_content"])
        self.mutate(current)
        reasons = [{"item_id": item.id, "reason": "按范围调整", "evidence_ids": ["e1"]}
                   for section in current.sections for item in section.items]
        return Completion(schema(reply="已按范围整理。", content=current, reasons=reasons), {})


def service_for(tmp_path, mutate):
    from app.resume_agent import AgentService

    store = ResumeStore(tmp_path / "resumes.sqlite3")
    jobs = JobStore(store)
    registry = ModelRegistry()
    registry.register(ProviderConfig(provider="custom", base_url="https://model.example/v1", model="fixture", api_key="secret"))
    client = ScopeClient(mutate)
    generation = GenerationService(store, jobs, registry, client)
    service = AgentService(SimpleNamespace(store=store, jobs=jobs, registry=registry, client=client, adopt=generation.adopt))
    record = store.create(content(), "manual", source_text=SOURCE)
    return service, store, record


def test_classification_stays_general_unless_one_lock_is_clear():
    from app.edit_scope import classify_edit_scope

    assert classify_edit_scope("改得更专业一点").kind == "general"
    assert classify_edit_scope("只改加粗，并且只改数字相关").kind == "general"
    assert classify_edit_scope("只改加粗").kind == "bold"
    assert classify_edit_scope("只改数字相关").kind == "numbers"
    assert classify_edit_scope("润色但保留数字").kind == "polish"
    assert classify_edit_scope("指定某一段").kind == "paragraph"
    assert classify_edit_scope("指定某一段").unresolved


def test_bold_only_can_change_highlights_and_undo_restores_the_sentence(tmp_path):
    from app.resume_agent import AgentMessageInput

    def mutate(current):
        current.sections[0].items[0].highlights = ["查询接口"]

    service, store, record = service_for(tmp_path, mutate)
    from app.resume_agent import AgentTargetInput

    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改加粗")))
    assert result["resume"].revision == 2
    item = result["resume"].content.sections[0].items[0]
    assert item.text == "使用 Java 完成查询接口，响应时间 500ms。"
    assert item.highlights == ["查询接口"]
    change = result["session"]["proposal"]["changes"][0]
    assert change["before"] == change["after"]
    assert "查询接口" in change["presentation_after"]
    undone = service.undo(session["id"])
    restored = undone["resume"].content.sections[0].items[0]
    assert restored.text == item.text
    assert restored.highlights == ["500ms"]
    assert store.get(record.id).revision == 3


def test_bold_only_rejects_body_changes_without_a_new_version(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    def mutate(current):
        current.sections[0].items[0].text = "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。"

    service, store, record = service_for(tmp_path, mutate)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改加粗")))
    assert result["resume"] is None
    assert store.get(record.id).revision == 1
    assert store.get(record.id).content.sections[0].items[0].text.startswith("使用 Java 完成查询接口，响应时间 500ms")
    assert any("只改加粗不能改正文" in message["text"] for message in result["session"]["messages"])
    assert result["session"]["proposal"]["state"] == "blocked"


def test_bold_phrase_missing_from_the_sentence_is_rejected(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    def mutate(current):
        current.sections[0].items[0].highlights = ["不在原句中"]

    service, store, record = service_for(tmp_path, mutate)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改加粗")))
    assert result["resume"] is None
    assert store.get(record.id).revision == 1
    assert any("已经出现在原句里" in message["text"] for message in result["session"]["messages"])


def test_number_scope_edits_only_numbered_sentences_and_rejects_invention(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    def mutate(current):
        current.sections[0].items[0].text = "使用 Java 完成查询接口，响应时间 300ms。"
        current.sections[0].items[0].highlights = ["300ms"]

    service, store, record = service_for(tmp_path, mutate)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    applied = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改数字相关，改成材料里的 300ms")))
    assert applied["resume"].revision == 2
    assert "300ms" in applied["resume"].content.sections[0].items[0].text
    assert applied["session"]["proposal"]["changes"][0]["before"] != applied["session"]["proposal"]["changes"][0]["after"]
    undone = service.undo(session["id"])
    assert "500ms" in undone["resume"].content.sections[0].items[0].text

    def invent(current):
        current.sections[0].items[0].text = "使用 Java 完成查询接口，点击率提升 20%。"
        current.sections[0].items[0].highlights = []

    service, store, record = service_for(tmp_path, invent)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    blocked = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改数字相关")))
    assert blocked["resume"] is None
    assert store.get(record.id).revision == 1
    assert "20%" not in store.get(record.id).content.sections[0].items[0].text
    assert any("没有保存" in message["text"] for message in blocked["session"]["messages"])

    def numberless(current):
        current.sections[0].items[1].text = "编写测试记录，未上线。"

    service, store, record = service_for(tmp_path, numberless)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    rejected = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改数字相关")))
    assert rejected["resume"] is None
    assert any("没有数字" in message["text"] for message in rejected["session"]["messages"])
    assert store.get(record.id).revision == 1


def test_paragraph_lock_leaves_other_paragraphs_unchanged(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    def mutate(current):
        current.sections[0].items[1].text = "编写测试记录，未上线。"

    service, store, record = service_for(tmp_path, mutate)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="只改第2段")))
    items = result["resume"].content.sections[0].items
    assert items[0].text == "使用 Java 完成查询接口，响应时间 500ms。"
    assert items[0].highlights == ["500ms"]
    assert items[1].text == "编写测试记录，未上线。"
    assert items[1].highlights == ["测试记录"]

    def spill(current):
        current.sections[0].items[0].highlights = ["查询接口"]

    service, store, record = service_for(tmp_path, spill)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    blocked = asyncio.run(service.post(session["id"], AgentMessageInput(text='只改「测试记录」')))
    assert blocked["resume"] is None
    assert store.get(record.id).content.sections[0].items[0].highlights == ["500ms"]
    assert any("指定段落以外" in message["text"] for message in blocked["session"]["messages"])


def test_polish_keeps_the_original_number_set(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    def mutate(current):
        current.sections[0].items[0].text = "把响应时间从 500ms 优化至 300ms。"

    service, _store, record = service_for(tmp_path, mutate)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    # The second number is introduced, so this request must be rejected.
    blocked = asyncio.run(service.post(session["id"], AgentMessageInput(text="润色但保留数字")))
    assert blocked["resume"] is None
    assert any("原有数字" in message["text"] for message in blocked["session"]["messages"])

    def keep(current):
        current.sections[0].items[0].text = "使用 Java 完成查询接口，并把响应时间写为 500ms。"

    service, _store, record = service_for(tmp_path, keep)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    applied = asyncio.run(service.post(session["id"], AgentMessageInput(text="润色但保留数字")))
    assert applied["resume"].revision == 2
    assert "500ms" in applied["resume"].content.sections[0].items[0].text
    assert "300" not in applied["resume"].content.sections[0].items[0].text


def test_vague_request_still_uses_the_fact_gate(tmp_path):
    from app.resume_agent import AgentMessageInput, AgentTargetInput

    def mutate(current):
        current.sections[0].items[0].text = "使用 Java 完成查询接口，将响应时间从 500ms 优化至 300ms。"

    service, store, record = service_for(tmp_path, mutate)
    session = service.create(AgentTargetInput(target_type="resume", target_id=record.id))
    result = asyncio.run(service.post(session["id"], AgentMessageInput(text="改得更具体一点")))
    assert result["session"]["proposal"]["scope"] == "general"
    assert result["resume"].revision == 2
    assert "300ms" in store.get(record.id).content.sections[0].items[0].text
