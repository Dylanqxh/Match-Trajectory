import pytest


def content(text="使用 Java 完成课程项目的订单查询接口"):
    from app.models import ResumeContent

    return ResumeContent.model_validate({
        "name": "测试用户", "target_role": "Java 后端",
        "sections": [{"id": "experience", "title": "项目经历",
                      "items": [{"id": "item-one", "text": text}]}],
    })


def test_revision_survives_restart_and_history_does_not_change(tmp_path):
    from app.store import ResumeStore

    store = ResumeStore(tmp_path / "resume.sqlite3")
    first = store.create(content(), "manual")
    changed = store.save(first.id, 1, content("补充了接口测试说明"))
    assert changed.revision == 2
    reopened = ResumeStore(tmp_path / "resume.sqlite3")
    assert reopened.get(first.id).content.sections[0].items[0].text == "补充了接口测试说明"
    assert reopened.history(first.id)[0].content.sections[0].items[0].text == "使用 Java 完成课程项目的订单查询接口"


def test_stale_save_and_confirmation_cannot_overwrite_new_content(tmp_path):
    from app.store import Conflict, ResumeStore

    store = ResumeStore(tmp_path / "resume.sqlite3")
    row = store.create(content(), "manual")
    store.save(row.id, 1, content("新版本"))
    with pytest.raises(Conflict):
        store.save(row.id, 1, content("旧标签页"))
    with pytest.raises(Conflict):
        store.confirm(row.id, 1)
    assert store.get(row.id).content.sections[0].items[0].text == "新版本"


def test_saving_invalidates_confirmation_and_creates_new_fact_revision(tmp_path):
    from app.store import ResumeStore

    store = ResumeStore(tmp_path / "resume.sqlite3")
    row = store.create(content(), "manual")
    confirmed = store.confirm(row.id, 1)
    assert confirmed.confirmed_revision == 1
    new = store.save(row.id, 1, content("改为本人真实完成的任务"))
    assert new.confirmed_revision is None
    assert new.facts[0].id != row.facts[0].id
    assert new.facts[0].text == "改为本人真实完成的任务"


def test_demo_origin_cannot_be_removed_by_editing(tmp_path):
    from app.store import ResumeStore

    store = ResumeStore(tmp_path / "resume.sqlite3")
    row = store.create(content(), "demo")
    assert store.save(row.id, 1, content("依然是虚构例子")).origin == "demo"


def test_empty_or_duplicate_bullets_and_overlong_content_are_rejected():
    from pydantic import ValidationError
    from app.models import ResumeContent

    with pytest.raises(ValidationError):
        content("   ")
    with pytest.raises(ValidationError):
        content("字" * 4001)
    with pytest.raises(ValidationError):
        ResumeContent.model_validate({"sections": [{"id": "a", "title": "经历", "items": [
            {"id": "same", "text": "一"}, {"id": "same", "text": "二"}]}]})


def test_unknown_resume_is_not_created_by_save(tmp_path):
    from app.store import NotFound, ResumeStore

    store = ResumeStore(tmp_path / "resume.sqlite3")
    with pytest.raises(NotFound):
        store.save("missing", 1, content())
    assert store.list() == []
