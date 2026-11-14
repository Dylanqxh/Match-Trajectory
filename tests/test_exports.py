from io import BytesIO

import pytest
from docx import Document

from tests_support import new_client


def test_html_escapes_user_content_and_does_not_make_external_requests():
    from app.models import ResumeContent
    from app.rendering import render_html, resume_fit_script

    html = render_html(ResumeContent(name='<script>alert("x")</script>', summary='<img src="https://bad.example/x">'))
    assert '<script>alert("x")</script>' not in html
    assert '<script src="/resume-fit.js" defer></script>' in html
    assert "<script>" not in html
    assert '<img src="https://bad.example' not in html
    assert "&lt;script&gt;" in html
    assert "content.style.width" not in resume_fit_script()
    assert "content.style.zoom" not in resume_fit_script()
    assert "@page{size:A4;margin:0}" in html
    assert "padding:8mm" in html


def test_preview_fitter_is_served_as_same_origin_javascript(tmp_path):
    with new_client(tmp_path) as client:
        response = client.get("/resume-fit.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert "data-fit-ready" not in response.text
    assert "fitReady" in response.text


def test_renderer_emphasizes_existing_small_heading_and_metric_without_rewriting_text():
    import re

    from app.models import Item, ResumeContent, Section
    from app.rendering import render_html

    text = "分层解耦：保持主流程不变，统一处理任务接入、校验与交付，计划准确率达到 99.8%。"
    html = render_html(ResumeContent(sections=[
        Section(id="project", title="项目", kind="project", items=[Item(id="item", text=text)])
    ]))

    assert "<strong>分层解耦</strong>" in html
    assert "<strong>计划准确率达到 99.8%</strong>" in html
    rendered = re.sub(r"<[^>]+>", "", html)
    assert text in rendered


def test_current_version_exports_directly_without_confirmation(tmp_path):
    with new_client(tmp_path) as client:
        row = client.post("/api/demo").json()
        url = f"/api/resumes/{row['id']}/exports"
        result = client.post(url, json={"format": "docx", "expected_revision": 1})
        assert result.status_code == 200
        text = "\n".join(p.text for p in Document(BytesIO(result.content)).paragraphs)
        assert "草稿" not in text and "虚构" in text
        assert "本人完成预约查询" in text


def test_ai_review_state_is_advisory_and_does_not_block_export(tmp_path):
    from app.models import AIInfo, Item, ResumeContent, Section, resume_hash

    with new_client(tmp_path) as client:
        content = ResumeContent(name="真实输入", contact="me@example.com", target_role="测试工程师", sections=[
            Section(id="work", title="测试经历", kind="work", items=[Item(id="case", text="编写接口测试用例并记录缺陷。")])
        ])
        info = AIInfo(job_id="job", review_job_id="job", review_status="blocked", content_hash=resume_hash(content),
                      skill_version="test", issues=[{"item_id": "case", "severity": "blocking", "code": "review", "message": "请核对"}])
        row = client.app.state.store.create(content, "ai", "编写接口测试用例并记录缺陷。", ai=info)

        result = client.post(f"/api/resumes/{row.id}/exports", json={"format": "docx", "expected_revision": 1})

        assert result.status_code == 200
        assert "编写接口测试用例并记录缺陷" in "\n".join(p.text for p in Document(BytesIO(result.content)).paragraphs)


def test_formal_docx_is_editable_and_matches_confirmed_content(tmp_path):
    with new_client(tmp_path) as client:
        row = client.post("/api/resumes", json={"name": "真实输入", "contact": "me@example.com", "source_text": "完成订单查询接口"}).json()
        result = client.post(f"/api/resumes/{row['id']}/exports", json={"format": "docx", "expected_revision": 1})
        assert result.status_code == 200
        doc = Document(BytesIO(result.content))
        assert any(p.text == "完成订单查询接口" for p in doc.paragraphs)
        assert "草稿" not in "\n".join(p.text for p in doc.paragraphs)
        assert list((tmp_path / "exports").glob("*.docx"))


def test_changed_resume_cannot_be_published_using_old_confirmation(tmp_path, monkeypatch):
    from app import exports

    with new_client(tmp_path) as client:
        row = client.post("/api/demo").json()
        client.post(f"/api/resumes/{row['id']}/confirm", json={"expected_revision": 1})
        original = exports.render_in_worker

        def concurrent_edit(payload):
            result = original(payload)
            current = client.app.state.store.get(row["id"])
            client.app.state.store.save(row["id"], 1, current.content.model_copy(update={"name": "另一标签页"}))
            return result

        monkeypatch.setattr(exports, "render_in_worker", concurrent_edit)
        response = client.post(f"/api/resumes/{row['id']}/exports", json={"format": "docx", "expected_revision": 1})
        assert response.status_code == 409
        assert not list((tmp_path / "exports").glob("*.docx"))


def test_blank_framework_cannot_be_formal_resume(tmp_path):
    with new_client(tmp_path) as client:
        row = client.post("/api/resumes", json={"target_role": "产品经理"}).json()
        client.post(f"/api/resumes/{row['id']}/confirm", json={"expected_revision": 1})
        response = client.post(f"/api/resumes/{row['id']}/exports", json={"format": "docx", "expected_revision": 1})
        assert response.status_code == 422


def test_worker_timeout_is_bounded():
    import sys

    from app.processes import WorkerFailure, run_worker

    with pytest.raises(WorkerFailure, match="超时"):
        run_worker([sys.executable, "-c", "import time; time.sleep(30)"], b"", timeout=0.2)


def test_repeated_exports_preserve_previously_delivered_file(tmp_path, monkeypatch):
    from app import exports
    from app.models import ExportRequest

    with new_client(tmp_path) as client:
        row = client.post("/api/demo").json()
        store = client.app.state.store
        store.confirm(row["id"], 1)
        original = exports.render_in_worker
        export_count = 0

        def render_with_metadata(payload):
            nonlocal export_count
            export_count += 1
            doc = Document(BytesIO(original(payload)))
            doc.core_properties.title = f"Export {export_count}"
            buffer = BytesIO()
            doc.save(buffer)
            return buffer.getvalue()

        monkeypatch.setattr(exports, "render_in_worker", render_with_metadata)
        request = ExportRequest(format="docx", expected_revision=1)
        first = exports.export_resume(store, tmp_path, row["id"], request)
        first_bytes = first.read_bytes()
        second = exports.export_resume(store, tmp_path, row["id"], request)
        assert first.read_bytes() == first_bytes
        assert first != second
