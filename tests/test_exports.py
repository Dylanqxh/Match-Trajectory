from io import BytesIO

import pytest
from docx import Document

from tests_support import new_client


def test_html_escapes_user_content_and_does_not_make_external_requests():
    from app.models import ResumeContent
    from app.rendering import render_html

    html = render_html(ResumeContent(name='<script>alert("x")</script>', summary='<img src="https://bad.example/x">'))
    assert "<script>" not in html
    assert '<img src="https://bad.example' not in html
    assert "&lt;script&gt;" in html


def test_export_requires_confirmation_and_draft_is_explicit(tmp_path):
    with new_client(tmp_path) as client:
        row = client.post("/api/demo").json()
        url = f"/api/resumes/{row['id']}/exports"
        assert client.post(url, json={"format": "docx", "expected_revision": 1}).status_code == 409
        result = client.post(url, json={"format": "docx", "expected_revision": 1, "draft": True})
        assert result.status_code == 200
        text = "\n".join(p.text for p in Document(BytesIO(result.content)).paragraphs)
        assert "草稿" in text and "虚构" in text
        assert "本人完成预约查询" in text


def test_formal_docx_is_editable_and_matches_confirmed_content(tmp_path):
    with new_client(tmp_path) as client:
        row = client.post("/api/resumes", json={"name": "真实输入", "contact": "me@example.com", "source_text": "完成订单查询接口"}).json()
        client.post(f"/api/resumes/{row['id']}/confirm", json={"expected_revision": 1})
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
