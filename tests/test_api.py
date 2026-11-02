from fastapi.testclient import TestClient


def local_client(tmp_path):
    from app.main import create_app

    return TestClient(create_app(tmp_path), base_url="http://127.0.0.1")


def test_private_data_requires_local_session_and_rejects_cross_origin(tmp_path):
    with local_client(tmp_path) as client:
        assert client.get("/api/resumes").status_code == 401
        assert client.get("/api/session").status_code == 200
        assert client.get("/api/resumes").json() == []
        response = client.post("/api/demo", headers={"origin": "https://untrusted.example"})
        assert response.status_code == 403
        assert client.get("/api/resumes").json() == []


def test_create_edit_reload_and_conflict_preserve_user_text(tmp_path):
    with local_client(tmp_path) as client:
        client.get("/api/session")
        created = client.post("/api/resumes", json={"name": "李明", "target_role": "算法", "source_text": "做过分类实验，没有上线部署"})
        assert created.status_code == 201
        row = created.json()
        assert row["origin"] == "manual"
        assert row["content"]["sections"][0]["items"][0]["text"] == "做过分类实验，没有上线部署"
        row["content"]["name"] = "李明明"
        saved = client.put(f"/api/resumes/{row['id']}", json={"expected_revision": 1, "content": row["content"]})
        assert saved.json()["revision"] == 2
        assert client.post(f"/api/resumes/{row['id']}/confirm", json={"expected_revision": 1}).status_code == 409
        assert client.get(f"/api/resumes/{row['id']}").json()["content"]["name"] == "李明明"
        assert len(client.get(f"/api/resumes/{row['id']}/history").json()) == 2


def test_demo_is_labelled_fictional_and_input_cannot_claim_ai_review(tmp_path):
    with local_client(tmp_path) as client:
        client.get("/api/session")
        row = client.post("/api/demo").json()
        assert row["origin"] == "demo"
        assert all(fact["source"] == "fictional_demo" for fact in row["facts"])
        invalid = client.post("/api/resumes", json={"name": "测试", "ai_review": "passed"})
        assert invalid.status_code == 422


def test_oversize_material_and_bad_host_are_rejected(tmp_path):
    with local_client(tmp_path) as client:
        client.get("/api/session")
        assert client.post("/api/resumes", json={"source_text": "字" * 20001}).status_code == 422
        assert client.get("/api/resumes", headers={"host": "attacker.example"}).status_code == 400


def test_validation_errors_do_not_echo_submitted_secrets(tmp_path):
    with local_client(tmp_path) as client:
        client.get("/api/session")
        response = client.post("/api/resumes", json={"unexpected": "secret-test-value"})
        assert response.status_code == 422
        assert "secret-test-value" not in response.text
