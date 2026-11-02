from fastapi.testclient import TestClient


def new_client(tmp_path):
    from app.main import create_app

    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    client.get("/api/session")
    return client
